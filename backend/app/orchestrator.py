"""Orchestrator: wires all components and runs the control loop.

Owns the live state, the mutable overrides, and the WebSocket broadcast fan-out.
The control cycle is intentionally fail-soft: any component failure logs and the
inverter keeps its last safe configuration (the engine never relies on being
alive for safety).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from pathlib import Path

from .adapters.ha_entity import HAEntityAdapter
from .config import AppConfig, Settings
from .config_store import ConfigStore
from .control.executor import Executor
from .engine.rules import RuleEngine
from .forecast.service import ForecastService
from .grid.reactive import ReactiveGrid
from .i18n.skip_keys import SKIP_ALREADY_SET
from .ha.client import HAClient
from .ha.heartbeat import HAHeartbeat
from .ha.users import HAAdminResolver
from .ingest.collector import Collector
from .models import (
    BatterySummary,
    Capability,
    Decision,
    ExecutionResult,
    GridStats,
    Override,
    ShedResult,
    SystemStatus,
    Telemetry,
    utcnow,
)
from .demo import synthetic_telemetry
from .shed_snapshots import ShedSnapshotStore
from .subsystems import deployment_profile, plan_grid_charge, plan_optimization, plan_shedding
from .storage import repo
from .storage.db import close_db, init_db

log = logging.getLogger("orchestrator")


class Orchestrator:
    def __init__(self, settings: Settings, store: ConfigStore) -> None:
        self.settings = settings
        self.store = store
        self.cfg: AppConfig = store.load()

        base_url, token, verify_ssl = self._resolve_ha()
        self.ha = HAClient(base_url, token, verify_ssl)
        self.heartbeat = HAHeartbeat(self.ha)
        self.adapter = HAEntityAdapter(self.ha, self.cfg.inverter)
        self.forecast = ForecastService(self.cfg, settings)
        self.collector = Collector(
            self.ha,
            self.adapter,
            self.cfg.inverter.read.grid_present,
            on_grid_change=self._on_grid_change,
            temp_entity=self.cfg.forecast.temperature.ha_entity or None,
        )

        # Components that are cheap and safe to rebuild on config change.
        self.reactive: ReactiveGrid
        self.engine: RuleEngine
        self.executor: Executor
        self._mpc = None
        self.snapshot_store = ShedSnapshotStore(settings.data_dir)
        self._build_engine_components()

        # Where learned model + config overrides live.
        self._model_path = str(Path(settings.data_dir) / "model.json")

        # Mutable runtime state.
        self.shadow_mode: bool = settings.shadow_mode
        self.paused_shedding: bool = False
        self.paused_grid_charge: bool = False
        self.paused_optimization: bool = False
        self.override = Override()
        self.latest_decision: Decision | None = None
        self.latest_results: list[ExecutionResult] = []
        self.latest_shed_results: list[ShedResult] = []
        self.latest_grid_stats: GridStats | None = None
        self._last_grid_charge_amps: float | None = None

        self._subscribers: set[asyncio.Queue] = set()
        self._stream_task: asyncio.Task | None = None
        self._cycle_lock = asyncio.Lock()
        self._scheduler = None
        self._admin_resolver: HAAdminResolver | None = None

    def set_admin_resolver(self, resolver: HAAdminResolver | None) -> None:
        self._admin_resolver = resolver

    def _resolve_ha(self) -> tuple[str, str, bool]:
        """HA connection: UI config wins when set, else environment/Supervisor."""
        ha = self.cfg.ha
        if ha.base_url and ha.token:
            return ha.base_url, ha.token, ha.verify_ssl
        return (
            self.settings.ha_base_url,
            self.settings.ha_token,
            self.settings.ha_verify_ssl,
        )

    async def _reconnect_ha(self) -> None:
        """Tear down and rebuild the HA client + live stream with new credentials."""
        base_url, token, verify_ssl = self._resolve_ha()
        log.info("Reconnecting to Home Assistant at %s", base_url)
        if self._stream_task:
            self._stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stream_task
            self._stream_task = None
        with contextlib.suppress(Exception):
            await self.ha.aclose()
        self.ha = HAClient(base_url, token, verify_ssl)
        if self._admin_resolver is not None:
            self._admin_resolver.set_ha(self.ha)
        self.heartbeat.set_ha(self.ha)
        self.adapter.set_ha(self.ha)
        self.collector.set_ha(self.ha)
        self._build_engine_components()  # executor picks up the new client
        with contextlib.suppress(Exception):
            await self.ha.ping()
        with contextlib.suppress(Exception):
            await self.collector.prime()
        self._stream_task = asyncio.create_task(self.collector.run_stream_safe())

    def _build_engine_components(self) -> None:
        """(Re)create stateless engine/control components from current cfg."""
        cfg = self.cfg
        self.reactive = ReactiveGrid(
            cfg.battery,
            cfg.reserve,
            cfg.grid_charge,
            cfg.site.timezone,
            self.forecast.resolved_timezone,
        )
        self.reactive.update_config(
            cfg.battery,
            cfg.reserve,
            cfg.grid_charge,
            cfg.site.timezone,
            self.forecast.resolved_timezone,
            cfg.engine.priority_order,
        )
        from .forecast.helpers import total_kwp

        self.engine = RuleEngine(
            cfg.battery,
            cfg.reserve,
            cfg.engine,
            self.reactive,
            cfg.load_shedding,
            cfg.grid_charge,
        )
        self.engine.set_total_kwp(total_kwp(cfg.forecast.arrays))
        self.executor = Executor(
            self.adapter,
            self.ha,
            cfg.battery,
            cfg.control,
            cfg.grid_charge,
            self.snapshot_store,
        )
        self._mpc = self._try_load_mpc() if cfg.engine.mode == "mpc" and cfg.engine.enabled else None

    def _all_shed_power_entities(self) -> set[str]:
        return {
            e
            for tier in self.cfg.load_shedding.tiers
            for e in tier.entity_ids()
        }

    def _prune_shed_snapshots(self) -> None:
        self.snapshot_store.prune(self._all_shed_power_entities())

    # ------------------------------------------------------------- lifecycle --
    async def setup(self) -> None:
        await init_db(self.settings.database_url)
        await self.collector.prime()
        # Restore previously learned model (bias + load profile), if any.
        if self.forecast.load_model(self._model_path):
            log.info("Restored learned model from %s", self._model_path)
        from .runtime_state import load as load_runtime_state

        saved = load_runtime_state(self.settings.data_dir)
        if "paused_shedding" in saved:
            self.paused_shedding = bool(saved["paused_shedding"])
        if "paused_grid_charge" in saved:
            self.paused_grid_charge = bool(saved["paused_grid_charge"])
        if "paused_optimization" in saved:
            self.paused_optimization = bool(saved["paused_optimization"])
        elif saved.get("paused"):
            self.paused_shedding = True
            self.paused_grid_charge = True
            self.paused_optimization = True
        if "shadow_mode" in saved:
            self.shadow_mode = bool(saved["shadow_mode"])
        if saved.get("override"):
            with contextlib.suppress(Exception):
                self.override = Override(**saved["override"])
        self._apply_pause_override(self.override)
        if self.settings.demo_mode:
            log.warning(
                "DEMO_MODE enabled — synthetic telemetry only; do not use in production."
            )
            self._inject_demo_telemetry()
        elif await self.ha.ping():
            log.info("Home Assistant reachable.")
        else:
            log.warning("Home Assistant not reachable yet; will keep retrying.")
        # Best-effort initial forecast + sample (don't crash startup on failure).
        with contextlib.suppress(Exception):
            await self.forecast.refresh()
        if self.settings.demo_mode:
            await self._control_cycle_body()
        else:
            with contextlib.suppress(Exception):
                await self.collector.sample()
            telemetry = self.collector.latest
            await self._refresh_grid_stats(
                telemetry.grid_present if telemetry else None
            )
            self._stream_task = asyncio.create_task(self.collector.run_stream_safe())
        await self._pulse_heartbeat()
        log.info("Orchestrator ready (shadow_mode=%s).", self.shadow_mode)

    def _grid_charge_writes_available(self) -> bool:
        return self._grid_charge_mapped()

    @property
    def paused(self) -> bool:
        return (
            self.paused_shedding
            and self.paused_grid_charge
            and self.paused_optimization
        )

    @paused.setter
    def paused(self, value: bool) -> None:
        self.paused_shedding = value
        self.paused_grid_charge = value
        self.paused_optimization = value

    @property
    def shedding_active(self) -> bool:
        return self.cfg.load_shedding.enabled and not self.paused_shedding

    @property
    def grid_charge_active(self) -> bool:
        return (
            self.cfg.grid_charge.enabled
            and self.cfg.engine.enabled
            and not self.paused_grid_charge
        )

    def grid_charge_writes_allowed(self) -> bool:
        if not self.cfg.grid_charge.enabled:
            return False
        if self.override.force_grid_charge is True:
            return True
        return self.cfg.engine.enabled and not self.paused_grid_charge

    @property
    def optimization_active(self) -> bool:
        return self.cfg.engine.enabled and not self.paused_optimization

    def _plan_flags(self) -> tuple[bool, bool, bool]:
        return (
            plan_optimization(self.cfg),
            plan_grid_charge(self.cfg),
            plan_shedding(self.cfg),
        )

    def _grid_charge_mapped(self) -> bool:
        w = self.cfg.inverter.write
        return bool(w.grid_charge_enable or w.max_grid_charge_current)

    async def _pulse_heartbeat(self) -> None:
        fs = self.cfg.fail_safe
        if not fs.heartbeat_enabled:
            return
        with contextlib.suppress(Exception):
            await self.heartbeat.pulse(fs.heartbeat_entity)

    async def shutdown(self) -> None:
        if self.cfg.fail_safe.shutdown_failsafe_enabled and self._grid_charge_mapped():
            async with self._cycle_lock:
                prev_shadow = self.shadow_mode
                self.shadow_mode = False
                try:
                    await self.executor.apply_grid_charge_at_max()
                except Exception as e:  # noqa: BLE001
                    log.warning("Shutdown fail-safe failed: %s", e)
                finally:
                    self.shadow_mode = prev_shadow
        if self._stream_task:
            self._stream_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._stream_task
        await self.ha.aclose()
        await close_db()

    def _try_load_mpc(self):
        try:
            from .engine.mpc import MPCEngine  # noqa: PLC0415

            from .forecast.helpers import total_kwp

            return MPCEngine(
                self.cfg.battery,
                self.cfg.reserve,
                self.cfg.engine,
                self.cfg.load_shedding,
                self.cfg.grid_charge,
                total_kwp=total_kwp(self.cfg.forecast.arrays),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("MPC unavailable (%s); using rule engine.", e)
            return None

    async def reload_config(self, patch: dict) -> AppConfig:
        """Apply a UI config patch, persist it, and hot-reload components."""
        old_ha = self._resolve_ha()
        async with self._cycle_lock:
            self.cfg = self.store.update(patch)
            # Update live components in place (preserve cache + learned model).
            self.adapter.update_config(self.cfg.inverter)
            self.collector.set_grid_entity(self.cfg.inverter.read.grid_present)
            self.collector.set_temp_entity(self.cfg.forecast.temperature.ha_entity or None)
            self.forecast.update_config(self.cfg)
            self._build_engine_components()
            self._prune_shed_snapshots()
            self._reschedule_jobs()
            if self._resolve_ha() != old_ha:
                await self._reconnect_ha()
            await self._control_cycle_body()
        return self.cfg

    async def reset_config(self) -> AppConfig:
        old_ha = self._resolve_ha()
        async with self._cycle_lock:
            self.cfg = self.store.reset()
            self.adapter.update_config(self.cfg.inverter)
            self.collector.set_grid_entity(self.cfg.inverter.read.grid_present)
            self.collector.set_temp_entity(self.cfg.forecast.temperature.ha_entity or None)
            self.forecast.update_config(self.cfg)
            self._build_engine_components()
            self._prune_shed_snapshots()
            self.override = Override()
            self.paused_shedding = False
            self.paused_grid_charge = False
            self.paused_optimization = False
            self.shadow_mode = self.settings.shadow_mode
            self._save_runtime_state()
            if self._resolve_ha() != old_ha:
                await self._reconnect_ha()
            await self._control_cycle_body()
        return self.cfg

    def attach_scheduler(self, scheduler) -> None:  # noqa: ANN001
        self._scheduler = scheduler

    def _reschedule_jobs(self) -> None:
        if self._scheduler is None:
            return
        from .scheduler import reschedule_jobs

        reschedule_jobs(self._scheduler, self)

    @property
    def model_path(self) -> str:
        return self._model_path

    # ----------------------------------------------------------------- loops --
    async def control_cycle(self) -> Decision | None:
        """One evaluation: sense -> decide -> (maybe) act -> broadcast."""
        async with self._cycle_lock:
            return await self._control_cycle_body()

    def _inject_demo_telemetry(self) -> Telemetry:
        telemetry = synthetic_telemetry()
        self.collector.set_latest(telemetry)
        return telemetry

    async def _demo_sample(self) -> Telemetry:
        telemetry = synthetic_telemetry()
        self.collector.set_latest(telemetry)
        with contextlib.suppress(Exception):
            await repo.save_telemetry(telemetry)
        return telemetry

    async def _control_cycle_body(self) -> Decision | None:
        if self.settings.demo_mode:
            telemetry = await self._demo_sample()
        else:
            try:
                telemetry = await self.collector.sample()
            except Exception as e:  # noqa: BLE001
                from .observability.metrics import metrics

                metrics.control_cycle_failures += 1
                log.warning("control_cycle telemetry failed: %s", e)
                telemetry = self.collector.latest
        if telemetry is None:
            await self._broadcast()
            await self._pulse_heartbeat()
            return None

        from .observability.metrics import metrics

        metrics.control_cycles += 1
        await self._refresh_grid_stats(telemetry.grid_present)

        forecast = self.forecast.current

        decision = self._decide(telemetry, forecast, self._telemetry_stale(telemetry))
        if not repo.decisions_audit_equal(self.latest_decision, decision):
            await repo.save_decision(decision)
        self.latest_decision = decision

        if self.grid_charge_writes_allowed() and decision.actions:
            try:
                self.latest_results = await self.executor.apply_decision(
                    decision, self.shadow_mode
                )
                self._update_last_grid_charge_amps(self.latest_results)
            except Exception as e:  # noqa: BLE001
                log.error("Executor failed: %s", e)
        else:
            self.latest_results = []
        if self.shedding_active and decision.shed_actions:
            try:
                self.latest_shed_results = await self.executor.apply_shed_actions(
                    decision.shed_actions,
                    self.shadow_mode,
                    tiers=self.cfg.load_shedding.tiers,
                )
            except Exception as e:  # noqa: BLE001
                log.error("Shedding executor failed: %s", e)
        else:
            self.latest_shed_results = []

        await self._broadcast()
        await self._pulse_heartbeat()
        return decision

    def _decide(self, telemetry, forecast, telemetry_stale: bool = False) -> Decision:
        plan_opt, plan_gc, plan_shed = self._plan_flags()
        kwargs = {
            "telemetry_stale": telemetry_stale,
            "last_grid_charge_amps": self._last_grid_charge_amps,
            "plan_optimization": plan_opt,
            "plan_grid_charge": plan_gc,
            "plan_shedding": plan_shed,
        }
        if self._mpc is not None and plan_opt:
            try:
                return self._mpc.decide(
                    telemetry,
                    forecast,
                    self.latest_grid_stats,
                    self.override,
                    self.shadow_mode,
                    self.reactive,
                    **kwargs,
                )
            except Exception as e:  # noqa: BLE001
                from .observability.metrics import metrics

                metrics.mpc_fallbacks += 1
                log.warning("MPC decide failed (%s); falling back to rules.", e)
        return self.engine.decide(
            telemetry,
            forecast,
            self.latest_grid_stats,
            self.override,
            self.shadow_mode,
            **kwargs,
        )

    def _update_last_grid_charge_amps(self, results: list[ExecutionResult]) -> None:
        for r in results:
            if r.capability is not Capability.MAX_GRID_CHARGE_CURRENT:
                continue
            if r.applied and isinstance(r.requested, (int, float)):
                self._set_last_grid_charge_amps(float(r.requested))
                return
            if r.skipped_reason in (SKIP_ALREADY_SET, "already set") and isinstance(r.requested, (int, float)):
                self._set_last_grid_charge_amps(float(r.requested))
                return

        if self.latest_decision and self.latest_decision.grid_charge is not None:
            plan = self.latest_decision.grid_charge
            if self.shadow_mode:
                amps = 0.0 if not plan.enabled else float(plan.target_amps)
                self._set_last_grid_charge_amps(amps)
                return
            if not plan.enabled:
                self._set_last_grid_charge_amps(0.0)

    def _set_last_grid_charge_amps(self, amps: float) -> None:
        self._last_grid_charge_amps = amps
        self.engine.set_last_grid_charge_amps(amps)

    def _telemetry_stale(self, telemetry) -> bool:  # noqa: ANN001
        if telemetry is None:
            return True
        age = (utcnow() - telemetry.ts).total_seconds()
        return age > self.cfg.control.ha_stale_after_seconds

    def _telemetry_age_seconds(self) -> float | None:
        t = self.collector.latest
        if t is None:
            return None
        return (utcnow() - t.ts).total_seconds()

    async def forecast_cycle(self) -> None:
        if not self.cfg.engine.enabled:
            return
        try:
            await self.forecast.refresh()
            self.forecast.save_model(self._model_path)  # persist learned state
            telemetry = self.collector.latest
            await self._refresh_grid_stats(
                telemetry.grid_present if telemetry else None
            )
            await self._broadcast()
        except Exception as e:  # noqa: BLE001
            from .observability.metrics import metrics

            metrics.forecast_refresh_failures += 1
            log.warning("forecast_cycle failed: %s", e)

    async def maintenance_cycle(self) -> None:
        with contextlib.suppress(Exception):
            # Keep enough history for the temperature regression / month factors;
            # never purge below the configured training window (plus a margin).
            training_days = self.cfg.forecast.temperature.training_days
            retention_days = max(60, training_days + 14)
            await repo.purge_older_than(days=retention_days)

    async def _on_grid_change(self, present: bool) -> None:
        """Grid just appeared/disappeared: re-evaluate immediately to exploit it."""
        log.info("Grid change -> immediate re-evaluation (present=%s).", present)
        await self._refresh_grid_stats(present)
        await self.control_cycle()

    async def _refresh_grid_stats(self, live_present: bool | None = None) -> None:
        try:
            self.latest_grid_stats = await self.reactive.compute_stats(
                live_present=live_present
            )
        except Exception as e:  # noqa: BLE001
            log.warning("grid stats failed: %s", e, exc_info=True)
            self.latest_grid_stats = None

    # ------------------------------------------------------------- overrides --
    def _apply_pause_override(self, ov: Override) -> None:
        if ov.pause_engine is not None:
            self.paused_shedding = ov.pause_engine
            self.paused_grid_charge = ov.pause_engine
            self.paused_optimization = ov.pause_engine
        if ov.pause_shedding is not None:
            self.paused_shedding = ov.pause_shedding
        if ov.pause_grid_charge is not None:
            self.paused_grid_charge = ov.pause_grid_charge
        if ov.pause_optimization is not None:
            self.paused_optimization = ov.pause_optimization

    def _apply_force_grid_coupling(self, ov: Override) -> None:
        """Couple force-on with pause; resume paths clear force back to optimizer (None)."""
        if ov.force_grid_charge is True:
            self.paused_grid_charge = True
        elif ov.pause_engine is False:
            self.override.force_grid_charge = None
        elif (
            ov.pause_grid_charge is False
            and ov.force_grid_charge is not True
            and ov.force_grid_charge is not False
        ):
            self.override.force_grid_charge = None

    async def apply_override(self, ov: Override) -> dict:
        if ov.kill_switch:
            async with self._cycle_lock:
                prev_shadow = self.shadow_mode
                self.shadow_mode = False
                results: list[ExecutionResult] = []
                # Shed-only sites may have grid charge disabled; still restore sheds and pause all.
                if self.grid_charge_active and self._grid_charge_writes_available():
                    results = await self.executor.kill_switch()
                shed_results = await self.executor.restore_all_sheds(
                    self.cfg.load_shedding.tiers, bypass_shadow=True
                )
                self.latest_results = results
                self.latest_shed_results = shed_results
                self.shadow_mode = prev_shadow
                self.paused_shedding = True
                self.paused_grid_charge = True
                self.paused_optimization = True
                self._save_runtime_state()
                await self._broadcast()
                return {
                    "kill_switch": True,
                    "applied": [r.model_dump(mode="json") for r in results],
                    "shed_restored": [r.model_dump(mode="json") for r in shed_results],
                }

        if ov.force_grid_charge is not None and not self.cfg.grid_charge.enabled:
            from .i18n import api_error

            raise api_error("api.override.grid_charge_disabled", 422)

        if ov.shadow_mode is not None:
            self.shadow_mode = ov.shadow_mode
        self._apply_pause_override(ov)
        if ov.reserve_soc is not None:
            self.override.reserve_soc = ov.reserve_soc
        if ov.force_grid_charge is not None:
            self.override.force_grid_charge = ov.force_grid_charge
        self._apply_force_grid_coupling(ov)

        async with self._cycle_lock:
            await self._control_cycle_body()
        self._save_runtime_state()
        return {
            "shadow_mode": self.shadow_mode,
            "paused": self.paused,
            "paused_shedding": self.paused_shedding,
            "paused_grid_charge": self.paused_grid_charge,
            "paused_optimization": self.paused_optimization,
            "reserve_soc": self.override.reserve_soc,
            "force_grid_charge": self.override.force_grid_charge,
        }

    def clear_overrides(self) -> dict:
        """Reset operator overrides and unpause (e.g. after kill switch)."""
        self.override = Override()
        self.paused_shedding = False
        self.paused_grid_charge = False
        self.paused_optimization = False
        self._save_runtime_state()
        return {
            "cleared": True,
            "paused": self.paused,
            "paused_shedding": self.paused_shedding,
            "paused_grid_charge": self.paused_grid_charge,
            "paused_optimization": self.paused_optimization,
            "shadow_mode": self.shadow_mode,
        }

    def _save_runtime_state(self) -> None:
        from .runtime_state import save as save_runtime_state

        save_runtime_state(
            self.settings.data_dir,
            {
                "paused": self.paused,
                "paused_shedding": self.paused_shedding,
                "paused_grid_charge": self.paused_grid_charge,
                "paused_optimization": self.paused_optimization,
                "shadow_mode": self.shadow_mode,
                "override": self.override.model_dump(),
            },
        )

    # --------------------------------------------------------------- status --
    def build_status(self) -> SystemStatus:
        telemetry = self.collector.latest
        stale = self._telemetry_stale(telemetry) if telemetry else True
        from .observability.capabilities import ml_available, mpc_available

        forecast = self.forecast.current
        bat = self.cfg.battery
        return SystemStatus(
            telemetry=telemetry,
            decision=self.latest_decision,
            grid_stats=self.latest_grid_stats,
            battery_summary=BatterySummary(
                capacity_kwh=bat.capacity_kwh,
                round_trip_efficiency=bat.round_trip_efficiency,
                max_soc_ceiling=bat.max_soc_ceiling,
                min_soc_floor=bat.min_soc_floor,
            ),
            ha_connected=(
                True
                if self.settings.demo_mode
                else self.ha.is_reachable(self.cfg.control.ha_stale_after_seconds)
            ),
            telemetry_stale=stale,
            telemetry_age_seconds=self._telemetry_age_seconds(),
            forecast_misconfigured=(
            not self.cfg.site.location_configured and self.cfg.engine.enabled
        ),
            forecast_degraded=forecast.degraded if forecast else False,
            forecast_provider=self.forecast.forecast_provider(),
            solcast_configured=self.forecast.solcast_configured(),
            engine_mode=self.cfg.engine.mode,
            engine_active="mpc" if self._mpc is not None else "rules",
            mpc_available=mpc_available(),
            ml_available=ml_available(),
            ml_load_enabled=self.settings.ml_load_enabled,
            mpc_unavailable=self.cfg.engine.mode == "mpc" and self._mpc is None,
            reserve_soc_override=self.override.reserve_soc,
            force_grid_charge_override=self.override.force_grid_charge,
            shadow_mode=self.shadow_mode,
            paused=self.paused,
            shedding_enabled=self.cfg.load_shedding.enabled,
            grid_charge_enabled=self.cfg.grid_charge.enabled,
            engine_enabled=self.cfg.engine.enabled,
            paused_shedding=self.paused_shedding,
            paused_grid_charge=self.paused_grid_charge,
            paused_optimization=self.paused_optimization,
            grid_charge_writes_available=self._grid_charge_writes_available(),
            deployment_profile=deployment_profile(self.cfg),
            timezone_config=self.cfg.site.timezone,
            timezone_resolved=self.forecast.resolved_timezone,
            last_updated=utcnow(),
        )

    # ------------------------------------------------------------ broadcast --
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=8)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def _broadcast(self) -> None:
        status = self.build_status().model_dump(mode="json")
        for q in list(self._subscribers):
            try:
                if q.full():
                    _ = q.get_nowait()
                q.put_nowait(status)
            except Exception:  # noqa: BLE001
                self._subscribers.discard(q)
