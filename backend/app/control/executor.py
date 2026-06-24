"""Executor: applies engine decisions to the inverter, safely.

Pipeline per action: hard-bounds check -> clamp -> shadow/watchdog gate ->
idempotency + rate limit -> write -> read-back verify -> persist result.
"""

from __future__ import annotations

import asyncio
import logging

from datetime import datetime

from ..adapters.base import InverterAdapter
from ..adapters.ha_entity import _to_bool
from ..config import BatteryConfig, ControlConfig, LoadTier
from ..ha.client import HAClient
from ..ha.device_discovery import discover_device_companions
from ..ha.entity_restore import (
    capture_entity_state,
    power_entity_was_on,
    restore_entity,
)
from ..models import (
    Capability,
    ControlAction,
    Decision,
    ExecutionResult,
    ShedAction,
    ShedResult,
    utcnow,
)
from ..observability.metrics import metrics
from ..shed_snapshots import EntitySnapshot, ShedSnapshotStore
from ..storage import repo
from .safety import SafetyGuard

log = logging.getLogger("control.executor")


class Executor:
    def __init__(
        self,
        adapter: InverterAdapter,
        ha: HAClient,
        battery: BatteryConfig,
        control: ControlConfig,
        snapshot_store: ShedSnapshotStore | None = None,
    ) -> None:
        self._adapter = adapter
        self._ha = ha
        self._battery = battery
        self._control = control
        self._guard = SafetyGuard(battery, control)
        self._snapshots = snapshot_store
        self._verify_delay = 1.5
        self._switch_last_write: dict[str, tuple[datetime, bool]] = {}

    def set_snapshot_store(self, store: ShedSnapshotStore) -> None:
        self._snapshots = store

    async def apply_decision(
        self, decision: Decision, shadow_mode: bool
    ) -> list[ExecutionResult]:
        results: list[ExecutionResult] = []
        for action in decision.actions:
            res = await self._apply_action(action, shadow_mode)
            results.append(res)
            await repo.save_execution(res)
            if res.applied:
                metrics.executor_writes_applied += 1
            else:
                metrics.executor_writes_skipped += 1
        return results

    async def _apply_action(
        self, action: ControlAction, shadow_mode: bool
    ) -> ExecutionResult:
        cap = action.capability
        requested = action.value

        if not self._adapter.supports(cap):
            return ExecutionResult(
                capability=cap, requested=requested, applied=False, verified=False,
                skipped_reason="capability not mapped",
            )

        reject = self._guard.violates_hard_bounds(cap, requested)
        if reject:
            log.warning("REJECT write %s=%s: %s", cap.value, requested, reject)
            return ExecutionResult(
                capability=cap, requested=requested, applied=False, verified=False,
                skipped_reason=f"hard-bound reject: {reject}",
            )

        value, note = self._guard.clamp(cap, requested)
        if note:
            log.info("Clamp %s: %s", cap.value, note)

        if self._ha.is_stale(self._control.ha_stale_after_seconds):
            return ExecutionResult(
                capability=cap, requested=value, applied=False, verified=False,
                skipped_reason="HA stale; watchdog blocked write",
            )

        try:
            current = await self._adapter.read_capability(cap)
        except Exception as e:  # noqa: BLE001
            current = None
            log.debug("read_capability(%s) failed pre-write: %s", cap.value, e)

        skip = self._guard.should_skip(cap, value, current)
        if skip:
            return ExecutionResult(
                capability=cap, requested=value, applied=False, verified=False,
                skipped_reason=skip,
            )

        if shadow_mode:
            log.info("[SHADOW] would write %s=%s (%s)", cap.value, value, action.reason)
            return ExecutionResult(
                capability=cap, requested=value, applied=False, verified=False,
                skipped_reason="shadow mode",
            )

        try:
            await self._adapter.apply(cap, value)
            self._guard.record_write(cap, value)
        except Exception as e:  # noqa: BLE001
            log.error("Write failed %s=%s: %s", cap.value, value, e)
            return ExecutionResult(
                capability=cap, requested=value, applied=False, verified=False,
                error=str(e),
            )

        verified = await self._verify(cap, value)
        if not verified:
            log.warning("Verify FAILED for %s=%s", cap.value, value)
        return ExecutionResult(
            capability=cap, requested=value, applied=True, verified=verified,
        )

    async def _verify(self, cap: Capability, value: float | bool) -> bool:
        await asyncio.sleep(self._verify_delay)
        try:
            readback = await self._adapter.read_capability(cap)
        except Exception as e:  # noqa: BLE001
            log.debug("verify read failed %s: %s", cap.value, e)
            return False
        if readback is None:
            return False
        return self._guard._equal(cap, value, readback)

    def _find_tier(self, tiers: list[LoadTier], tier_name: str) -> LoadTier | None:
        for t in tiers:
            if t.name == tier_name:
                return t
        return None

    async def _resolve_companion_ids(
        self, tier: LoadTier | None, power_entity: str
    ) -> list[str]:
        if tier is not None:
            configured = tier.companions_for(power_entity)
            if configured is not None:
                return configured
        try:
            discovered = await discover_device_companions(self._ha, power_entity)
            return [c.entity_id for c in discovered.companions]
        except Exception as e:  # noqa: BLE001
            log.warning("companion discovery for %s failed: %s", power_entity, e)
            return []

    async def _capture_shed_snapshot(
        self,
        power_entity: str,
        tier: LoadTier | None,
    ) -> tuple[bool, list[str]]:
        try:
            st = await self._ha.get_state(power_entity)
        except Exception as e:  # noqa: BLE001
            log.debug("shed snapshot read %s failed: %s", power_entity, e)
            st = None
        was_on = power_entity_was_on(st)
        companion_ids = await self._resolve_companion_ids(tier, power_entity)
        companions: dict[str, EntitySnapshot] = {}
        if was_on:
            for cid in companion_ids:
                snap = await capture_entity_state(self._ha, cid)
                if snap:
                    companions[cid] = snap
        if self._snapshots is not None:
            self._snapshots.capture(
                power_entity, was_on=was_on, companions=companions
            )
        return was_on, list(companions.keys())

    async def _restore_companions(
        self, snapshot_companions: dict[str, EntitySnapshot]
    ) -> tuple[list[str], dict[str, str]]:
        restored: list[str] = []
        errors: dict[str, str] = {}
        for eid, snap in snapshot_companions.items():
            try:
                await restore_entity(self._ha, eid, snap)
                restored.append(eid)
            except Exception as e:  # noqa: BLE001
                log.error("companion restore %s failed: %s", eid, e)
                errors[eid] = str(e)
        if restored:
            await asyncio.sleep(self._verify_delay)
        return restored, errors

    async def apply_shed_actions(
        self,
        actions: list[ShedAction],
        shadow_mode: bool,
        tiers: list[LoadTier] | None = None,
    ) -> list[ShedResult]:
        """Apply load-shedding switch states with snapshot/restore support."""
        tier_list = tiers or []
        results: list[ShedResult] = []
        for a in actions:
            res = await self._apply_shed(a, shadow_mode, tier_list)
            results.append(res)
            await repo.save_shed_execution(res)
            if res.applied:
                metrics.shed_writes_applied += 1
            else:
                metrics.shed_writes_skipped += 1
        return results

    async def _apply_shed(
        self,
        a: ShedAction,
        shadow_mode: bool,
        tiers: list[LoadTier],
    ) -> ShedResult:
        tier = self._find_tier(tiers, a.tier)
        companions_captured: list[str] = []
        companions_restored: list[str] = []
        companion_errors: dict[str, str] = {}

        if shadow_mode:
            companion_ids = await self._resolve_companion_ids(tier, a.entity)
            log.info(
                "[SHADOW] would set %s -> %s (%s); companions=%s",
                a.entity,
                a.desired_on,
                a.reason,
                companion_ids,
            )
            return ShedResult(
                tier=a.tier,
                entity=a.entity,
                desired_on=a.desired_on,
                applied=False,
                verified=False,
                skipped_reason="shadow mode",
            )

        if self._ha.is_stale(self._control.ha_stale_after_seconds):
            return ShedResult(
                tier=a.tier,
                entity=a.entity,
                desired_on=a.desired_on,
                applied=False,
                verified=False,
                skipped_reason="HA stale; watchdog blocked write",
            )

        # Restore path: check snapshot before shed capture
        if a.desired_on:
            snap = self._snapshots.get(a.entity) if self._snapshots else None
            if snap is None:
                return ShedResult(
                    tier=a.tier,
                    entity=a.entity,
                    desired_on=a.desired_on,
                    applied=False,
                    verified=False,
                    skipped_reason="no shed snapshot; not restoring",
                )
            if not snap.was_on:
                if self._snapshots:
                    self._snapshots.clear(a.entity)
                return ShedResult(
                    tier=a.tier,
                    entity=a.entity,
                    desired_on=a.desired_on,
                    applied=False,
                    verified=False,
                    skipped_reason="was off before shed",
                )

        # Shed path: capture snapshot before idempotency
        if not a.desired_on:
            _, companions_captured = await self._capture_shed_snapshot(a.entity, tier)

        try:
            st = await self._ha.get_state(a.entity)
            current = _to_bool(st.get("state")) if st else None
        except Exception as e:  # noqa: BLE001
            current = None
            log.debug("shed read %s failed: %s", a.entity, e)

        power_already_set = current is not None and current == a.desired_on

        last = self._switch_last_write.get(a.entity)
        if last is not None and not power_already_set:
            last_ts, last_val = last
            elapsed = (utcnow() - last_ts).total_seconds()
            if last_val == a.desired_on and elapsed < self._control.min_write_interval_seconds:
                if a.desired_on:
                    snap = self._snapshots.get(a.entity) if self._snapshots else None
                    if snap and snap.was_on:
                        companions_restored, companion_errors = (
                            await self._restore_companions(snap.companions)
                        )
                        if self._snapshots:
                            self._snapshots.clear(a.entity)
                return ShedResult(
                    tier=a.tier,
                    entity=a.entity,
                    desired_on=a.desired_on,
                    applied=False,
                    verified=False,
                    skipped_reason="recently written (unchanged)",
                    companions_captured=companions_captured,
                    companions_restored=companions_restored,
                    companion_errors=companion_errors,
                )

        applied = False
        verified = False
        error: str | None = None

        if a.desired_on:
            snap = self._snapshots.get(a.entity) if self._snapshots else None
            if not power_already_set:
                try:
                    await self._ha.toggle_entity(a.entity, True)
                    self._switch_last_write[a.entity] = (utcnow(), True)
                    applied = True
                except Exception as e:  # noqa: BLE001
                    log.error("shed write %s failed: %s", a.entity, e)
                    return ShedResult(
                        tier=a.tier,
                        entity=a.entity,
                        desired_on=a.desired_on,
                        applied=False,
                        verified=False,
                        error=str(e),
                    )
                await asyncio.sleep(self._verify_delay)
                try:
                    st = await self._ha.get_state(a.entity)
                    verified = bool(st) and _to_bool(st.get("state")) is True
                except Exception:  # noqa: BLE001
                    verified = False
            else:
                verified = True

            if snap and snap.was_on:
                companions_restored, companion_errors = await self._restore_companions(
                    snap.companions
                )
                if self._snapshots:
                    self._snapshots.clear(a.entity)
        else:
            if power_already_set:
                return ShedResult(
                    tier=a.tier,
                    entity=a.entity,
                    desired_on=a.desired_on,
                    applied=False,
                    verified=True,
                    skipped_reason="already set",
                    companions_captured=companions_captured,
                )
            try:
                await self._ha.toggle_entity(a.entity, False)
                self._switch_last_write[a.entity] = (utcnow(), False)
                applied = True
            except Exception as e:  # noqa: BLE001
                log.error("shed write %s failed: %s", a.entity, e)
                return ShedResult(
                    tier=a.tier,
                    entity=a.entity,
                    desired_on=a.desired_on,
                    applied=False,
                    verified=False,
                    error=str(e),
                    companions_captured=companions_captured,
                )
            await asyncio.sleep(self._verify_delay)
            try:
                st = await self._ha.get_state(a.entity)
                verified = bool(st) and _to_bool(st.get("state")) is False
            except Exception:  # noqa: BLE001
                verified = False

        return ShedResult(
            tier=a.tier,
            entity=a.entity,
            desired_on=a.desired_on,
            applied=applied,
            verified=verified,
            error=error,
            companions_captured=companions_captured,
            companions_restored=companions_restored,
            companion_errors=companion_errors,
        )

    async def apply_grid_charge_at_max(
        self,
        *,
        bypass_watchdog: bool = True,
    ) -> list[ExecutionResult]:
        log.warning("Applying fail-safe: grid charge ON at max current.")
        amps, _ = self._guard.clamp(
            Capability.MAX_GRID_CHARGE_CURRENT, self._battery.max_grid_charge_a
        )
        pairs: list[tuple[Capability, float | bool]] = [
            (Capability.GRID_CHARGE_ENABLE, True),
            (Capability.MAX_GRID_CHARGE_CURRENT, amps),
        ]
        return await self._apply_emergency_writes(pairs, bypass_watchdog=bypass_watchdog)

    async def kill_switch(self) -> list[ExecutionResult]:
        log.warning("KILL SWITCH engaged: grid charge at max current.")
        return await self.apply_grid_charge_at_max()

    async def _apply_emergency_writes(
        self,
        pairs: list[tuple[Capability, float | bool]],
        *,
        bypass_watchdog: bool,
    ) -> list[ExecutionResult]:
        results: list[ExecutionResult] = []
        for cap, requested in pairs:
            if not self._adapter.supports(cap):
                results.append(
                    ExecutionResult(
                        capability=cap,
                        requested=requested,
                        applied=False,
                        verified=False,
                        skipped_reason="capability not mapped",
                    )
                )
                continue

            reject = self._guard.violates_hard_bounds(cap, requested)
            if reject:
                log.warning("REJECT emergency write %s=%s: %s", cap.value, requested, reject)
                results.append(
                    ExecutionResult(
                        capability=cap,
                        requested=requested,
                        applied=False,
                        verified=False,
                        skipped_reason=f"hard-bound reject: {reject}",
                    )
                )
                continue

            value, note = self._guard.clamp(cap, requested)
            if note:
                log.info("Clamp %s: %s", cap.value, note)

            if (
                not bypass_watchdog
                and self._ha.is_stale(self._control.ha_stale_after_seconds)
            ):
                results.append(
                    ExecutionResult(
                        capability=cap,
                        requested=value,
                        applied=False,
                        verified=False,
                        skipped_reason="HA stale; watchdog blocked write",
                    )
                )
                continue

            try:
                await self._adapter.apply(cap, value)
                self._guard.record_write(cap, value)
                verified = await self._verify(cap, value)
                res = ExecutionResult(
                    capability=cap, requested=value, applied=True, verified=verified
                )
            except Exception as e:  # noqa: BLE001
                res = ExecutionResult(
                    capability=cap,
                    requested=value,
                    applied=False,
                    verified=False,
                    error=str(e),
                )
            results.append(res)
            await repo.save_execution(res)
        return results

    async def restore_all_sheds(
        self, tiers: list[LoadTier], bypass_shadow: bool = True
    ) -> list[ShedResult]:
        """Restore shed switches honoring was_on snapshots (e.g. kill switch)."""
        actions = [
            ShedAction(
                tier=t.name,
                entity=entity,
                desired_on=True,
                reason="Restore tier after emergency / kill switch.",
            )
            for t in tiers
            for entity in t.entity_ids()
        ]
        if not actions:
            return []
        return await self.apply_shed_actions(
            actions, shadow_mode=not bypass_shadow, tiers=tiers
        )
