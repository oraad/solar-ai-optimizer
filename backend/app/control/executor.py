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
    ) -> None:
        self._adapter = adapter
        self._ha = ha
        self._battery = battery
        self._control = control
        self._guard = SafetyGuard(battery, control)
        self._verify_delay = 1.5  # seconds to let the inverter settle before read-back
        # Per-entity last-write tracking for load-shedding switches.
        self._switch_last_write: dict[str, tuple[datetime, bool]] = {}

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

        # 1) Hard bounds: reject outright if dangerous.
        reject = self._guard.violates_hard_bounds(cap, requested)
        if reject:
            log.warning("REJECT write %s=%s: %s", cap.value, requested, reject)
            return ExecutionResult(
                capability=cap, requested=requested, applied=False, verified=False,
                skipped_reason=f"hard-bound reject: {reject}",
            )

        # 2) Clamp to safe range.
        value, note = self._guard.clamp(cap, requested)
        if note:
            log.info("Clamp %s: %s", cap.value, note)

        # 3) Watchdog: never write if HA is stale/unreachable.
        if self._ha.is_stale(self._control.ha_stale_after_seconds):
            return ExecutionResult(
                capability=cap, requested=value, applied=False, verified=False,
                skipped_reason="HA stale; watchdog blocked write",
            )

        # 4) Read current value for idempotency/verification.
        try:
            current = await self._adapter.read_capability(cap)
        except Exception as e:  # noqa: BLE001
            current = None
            log.debug("read_capability(%s) failed pre-write: %s", cap.value, e)

        # 5) Idempotency + EEPROM rate limit.
        skip = self._guard.should_skip(cap, value, current)
        if skip:
            return ExecutionResult(
                capability=cap, requested=value, applied=False, verified=False,
                skipped_reason=skip,
            )

        # 6) Shadow mode: log only, do not write.
        if shadow_mode:
            log.info("[SHADOW] would write %s=%s (%s)", cap.value, value, action.reason)
            return ExecutionResult(
                capability=cap, requested=value, applied=False, verified=False,
                skipped_reason="shadow mode",
            )

        # 7) Write.
        try:
            await self._adapter.apply(cap, value)
            self._guard.record_write(cap, value)
        except Exception as e:  # noqa: BLE001
            log.error("Write failed %s=%s: %s", cap.value, value, e)
            return ExecutionResult(
                capability=cap, requested=value, applied=False, verified=False,
                error=str(e),
            )

        # 8) Read-back verify (Deye TOU writes are known-flaky).
        verified = await self._verify(cap, value)
        if not verified:
            log.warning("Verify FAILED for %s=%s", cap.value, value)
        return ExecutionResult(
            capability=cap, requested=value, applied=True, verified=verified,
        )

    async def _verify(self, cap: Capability, value: float | bool | str) -> bool:
        await asyncio.sleep(self._verify_delay)
        try:
            readback = await self._adapter.read_capability(cap)
        except Exception as e:  # noqa: BLE001
            log.debug("verify read failed %s: %s", cap.value, e)
            return False
        if readback is None:
            return False
        return self._guard._equal(cap, value, readback)

    async def apply_shed_actions(
        self, actions: list[ShedAction], shadow_mode: bool
    ) -> list[ShedResult]:
        """Apply load-shedding switch states with watchdog/idempotency/verify."""
        results: list[ShedResult] = []
        for a in actions:
            res = await self._apply_shed(a, shadow_mode)
            results.append(res)
            await repo.save_shed_execution(res)
            if res.applied:
                metrics.shed_writes_applied += 1
            else:
                metrics.shed_writes_skipped += 1
        return results

    async def _apply_shed(self, a: ShedAction, shadow_mode: bool) -> ShedResult:
        if self._ha.is_stale(self._control.ha_stale_after_seconds):
            return ShedResult(
                tier=a.tier, entity=a.entity, desired_on=a.desired_on,
                applied=False, verified=False,
                skipped_reason="HA stale; watchdog blocked write",
            )

        # Idempotency: read current switch state.
        try:
            st = await self._ha.get_state(a.entity)
            current = _to_bool(st.get("state")) if st else None
        except Exception as e:  # noqa: BLE001
            current = None
            log.debug("shed read %s failed: %s", a.entity, e)

        if current is not None and current == a.desired_on:
            return ShedResult(
                tier=a.tier, entity=a.entity, desired_on=a.desired_on,
                applied=False, verified=True, skipped_reason="already set",
            )

        last = self._switch_last_write.get(a.entity)
        if last is not None:
            last_ts, last_val = last
            elapsed = (utcnow() - last_ts).total_seconds()
            if last_val == a.desired_on and elapsed < self._control.min_write_interval_seconds:
                return ShedResult(
                    tier=a.tier, entity=a.entity, desired_on=a.desired_on,
                    applied=False, verified=False,
                    skipped_reason="recently written (unchanged)",
                )

        if shadow_mode:
            log.info("[SHADOW] would set %s -> %s (%s)", a.entity, a.desired_on, a.reason)
            return ShedResult(
                tier=a.tier, entity=a.entity, desired_on=a.desired_on,
                applied=False, verified=False, skipped_reason="shadow mode",
            )

        try:
            await self._ha.toggle_entity(a.entity, a.desired_on)
            self._switch_last_write[a.entity] = (utcnow(), a.desired_on)
        except Exception as e:  # noqa: BLE001
            log.error("shed write %s failed: %s", a.entity, e)
            return ShedResult(
                tier=a.tier, entity=a.entity, desired_on=a.desired_on,
                applied=False, verified=False, error=str(e),
            )

        await asyncio.sleep(self._verify_delay)
        try:
            st = await self._ha.get_state(a.entity)
            verified = bool(st) and _to_bool(st.get("state")) == a.desired_on
        except Exception:  # noqa: BLE001
            verified = False
        return ShedResult(
            tier=a.tier, entity=a.entity, desired_on=a.desired_on,
            applied=True, verified=verified,
        )

    async def apply_grid_charge_at_max(
        self,
        *,
        bypass_watchdog: bool = True,
    ) -> list[ExecutionResult]:
        """Fail-safe: enable grid charge at max configured current.

        Bypasses rate limiting and the HA stale watchdog when ``bypass_watchdog``
        is True (emergency > wear). Never changes work mode.
        """
        log.warning("Applying fail-safe: grid charge ON at max current.")
        amps, _ = self._guard.clamp(
            Capability.MAX_GRID_CHARGE_CURRENT, self._battery.max_grid_charge_a
        )
        pairs: list[tuple[Capability, float | bool | str]] = [
            (Capability.GRID_CHARGE_ENABLE, True),
            (Capability.MAX_GRID_CHARGE_CURRENT, amps),
        ]
        return await self._apply_emergency_writes(pairs, bypass_watchdog=bypass_watchdog)

    async def kill_switch(self) -> list[ExecutionResult]:
        """Operator emergency: grid charge at max, then pause engine (orchestrator)."""
        log.warning("KILL SWITCH engaged: grid charge at max current.")
        return await self.apply_grid_charge_at_max()

    async def _apply_emergency_writes(
        self,
        pairs: list[tuple[Capability, float | bool | str]],
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
        """Turn all configured shed switches back on (e.g. after kill switch)."""
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
        return await self.apply_shed_actions(actions, shadow_mode=not bypass_shadow)
