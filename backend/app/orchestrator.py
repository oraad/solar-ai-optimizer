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
from .ha.client import HAClient
from .ha.heartbeat import HAHeartbeat
from .ha.users import HAAdminResolver
from .ingest.collector import Collector
from .models import (
    BatterySummary,
    Decision,
    ExecutionResult,
    GridStats,
    Override,
    ShedResult,
    SystemStatus,
    utcnow,
)
from .demo import synthetic_telemetry
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
        self._build_engine_components()

        # Where learned model + config overrides live.
        self._model_path = str(Path(settings.data_dir) / "model.json")

        # Mutable runtime state.
        self.shadow_mode: bool = settings.shadow_mode
        self.paused: bool = False
        self.override = Override()
        self.latest_decision: Decision | None = None
        self.latest_results: list[ExecutionResult] = []
        self.latest_shed_results: list[ShedResult] = []
        self.latest_grid_stats: GridStats | None = None

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
        self.reactive = ReactiveGrid(cfg.battery, cfg.reserve)
        from .forecast.helpers import total_kwp

        self.engine = RuleEngine(
            cfg.battery, cfg.reserve, cfg.engine, self.reactive, cfg.load_shedding
        )
        self.engine.set_total_kwp(total_kwp(cfg.forecast.arrays))
        self.executor = Executor(self.adapter, self.ha, cfg.battery, cfg.control)
        self._mpc = self._try_load_mpc() if cfg.engine.mode == "mpc" else None

    # ------------------------------------------------------------- lifecycle --
    async def setup(self) -> None:
        await init_db(self.settings.database_url)
        await self.collector.prime()
        # Restore previously learned model (bias + load profile), if any.
        if self.forecast.load_model(self._model_path):
            log.info("Restored learned model from %s", self._model_path)
        from .runtime_state import load as load_runtime_state

        saved = load_runtime_state(self.settings.data_dir)
        if "paused" in saved:
            self.paused = bool(saved["paused"])
        if "shadow_mode" in saved:
            self.shadow_mode = bool(saved["shadow_mode"])
        if saved.get("override"):
            with contextlib.suppress(Exception):
                self.override = Override(**saved["override"])
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
            self._stream_task = asyncio.create_task(self.collector.run_stream_safe())
        await self._pulse_heartbeat()
        log.info("Orchestrator ready (shadow_mode=%s).", self.shadow_mode)

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
            self._reschedule_jobs()
            self.override = Override()
            self.paused = False
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
        try:
            self.latest_grid_stats = await self.reactive.compute_stats(
                live_present=telemetry.grid_present
            )
        except Exception as e:  # noqa: BLE001
            log.debug("grid stats failed: %s", e)

        forecast = self.forecast.current

        decision = self._decide(telemetry, forecast, self._telemetry_stale(telemetry))
        self.latest_decision = decision
        await repo.save_decision(decision)

        if not self.paused:
            try:
                self.latest_results = await self.executor.apply_decision(
                    decision, self.shadow_mode
                )
            except Exception as e:  # noqa: BLE001
                log.error("Executor failed: %s", e)
        else:
            self.latest_results = []
        if not self.paused and decision.shed_actions:
            try:
                self.latest_shed_results = await self.executor.apply_shed_actions(
                    decision.shed_actions, self.shadow_mode
                )
            except Exception as e:  # noqa: BLE001
                log.error("Shedding executor failed: %s", e)
        else:
            self.latest_shed_results = []

        await self._broadcast()
        await self._pulse_heartbeat()
        return decision

    def _decide(self, telemetry, forecast, telemetry_stale: bool = False) -> Decision:
        if self._mpc is not None:
            try:
                return self._mpc.decide(
                    telemetry,
                    forecast,
                    self.latest_grid_stats,
                    self.override,
                    self.shadow_mode,
                    self.reactive,
                    telemetry_stale=telemetry_stale,
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
            telemetry_stale=telemetry_stale,
        )

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
        try:
            await self.forecast.refresh()
            self.forecast.save_model(self._model_path)  # persist learned state
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
        await self.control_cycle()

    # ------------------------------------------------------------- overrides --
    async def apply_override(self, ov: Override) -> dict:
        if ov.kill_switch:
            async with self._cycle_lock:
                prev_shadow = self.shadow_mode
                self.shadow_mode = False
                results = await self.executor.kill_switch()
                shed_results = await self.executor.restore_all_sheds(
                    self.cfg.load_shedding.tiers, bypass_shadow=True
                )
                self.latest_results = results
                self.latest_shed_results = shed_results
                self.shadow_mode = prev_shadow
                self.paused = True
                self._save_runtime_state()
                await self._broadcast()
                return {
                    "kill_switch": True,
                    "applied": [r.model_dump(mode="json") for r in results],
                    "shed_restored": [r.model_dump(mode="json") for r in shed_results],
                }

        if ov.shadow_mode is not None:
            self.shadow_mode = ov.shadow_mode
        if ov.pause_engine is not None:
            self.paused = ov.pause_engine
        if ov.reserve_soc is not None:
            self.override.reserve_soc = ov.reserve_soc
        if ov.force_grid_charge is not None:
            self.override.force_grid_charge = ov.force_grid_charge

        async with self._cycle_lock:
            await self._control_cycle_body()
        self._save_runtime_state()
        return {
            "shadow_mode": self.shadow_mode,
            "paused": self.paused,
            "reserve_soc": self.override.reserve_soc,
            "force_grid_charge": self.override.force_grid_charge,
        }

    def clear_overrides(self) -> dict:
        """Reset operator overrides and unpause (e.g. after kill switch)."""
        self.override = Override()
        self.paused = False
        self._save_runtime_state()
        return {
            "cleared": True,
            "paused": self.paused,
            "shadow_mode": self.shadow_mode,
        }

    def _save_runtime_state(self) -> None:
        from .runtime_state import save as save_runtime_state

        save_runtime_state(
            self.settings.data_dir,
            {
                "paused": self.paused,
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
            forecast_misconfigured=not self.cfg.forecast.location_configured,
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
