"""Multi-tier load shedding.

Sheds lower-priority loads as battery SOC falls and restores them as it
recovers, using per-tier hysteresis. When the grid is physically present, all
tiers are restored (the battery no longer needs protecting). This protects the
critical reserve by cutting discretionary draw before the battery is endangered.
"""

from __future__ import annotations

import logging

from ..config import LoadSheddingConfig
from ..models import ShedAction, Telemetry

log = logging.getLogger("engine.shedding")


class LoadSheddingController:
    def __init__(self, cfg: LoadSheddingConfig) -> None:
        self._cfg = cfg

    def plan(
        self, telemetry: Telemetry, telemetry_stale: bool = False
    ) -> list[ShedAction]:
        if not self._cfg.enabled or not self._cfg.tiers:
            return []

        actions: list[ShedAction] = []
        grid = telemetry.grid_present is True
        soc = telemetry.battery_soc
        conservative = soc is None or telemetry_stale

        # Shed lowest-priority tiers first for clear, ordered rationale.
        for tier in sorted(self._cfg.tiers, key=lambda t: t.priority):
            entities = tier.entity_ids()
            if not entities:
                continue
            if grid and self._cfg.restore_all_when_grid_present:
                for entity in entities:
                    actions.append(
                        ShedAction(
                            tier=tier.name,
                            entity=entity,
                            desired_on=True,
                            reason="Grid present: restore tier (battery not at risk).",
                        )
                    )
                continue
            if conservative:
                for entity in entities:
                    actions.append(
                        ShedAction(
                            tier=tier.name,
                            entity=entity,
                            desired_on=False,
                            reason=(
                                "SOC unknown or telemetry stale: shed "
                                f"'{tier.name}' conservatively."
                            ),
                        )
                    )
                continue
            if soc < tier.shed_below_soc:
                for entity in entities:
                    actions.append(
                        ShedAction(
                            tier=tier.name,
                            entity=entity,
                            desired_on=False,
                            reason=(
                                f"SOC {soc:.0f}% < {tier.shed_below_soc:.0f}%: "
                                f"shed '{tier.name}' to defend reserve."
                            ),
                        )
                    )
            elif soc >= tier.restore_above_soc:
                for entity in entities:
                    actions.append(
                        ShedAction(
                            tier=tier.name,
                            entity=entity,
                            desired_on=True,
                            reason=(
                                f"SOC {soc:.0f}% >= {tier.restore_above_soc:.0f}%: "
                                f"restore '{tier.name}'."
                            ),
                        )
                    )
            # Otherwise within the hysteresis band: leave the tier unchanged.
        return actions
