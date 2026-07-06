"""Multi-tier load shedding."""

from __future__ import annotations

import logging

from ..config import LoadSheddingConfig
from ..i18n import msg
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

        for tier in sorted(self._cfg.tiers, key=lambda t: t.priority):
            entities = tier.entity_ids()
            if not entities:
                continue
            if grid and self._cfg.restore_all_when_grid_present:
                if not tier.restore_on_grid:
                    continue
                for entity in entities:
                    actions.append(
                        ShedAction(
                            tier=tier.name,
                            entity=entity,
                            desired_on=True,
                            reason=msg("engine.shed.restore_grid"),
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
                            reason=msg("engine.shed.conservative", tier=tier.name),
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
                            reason=msg(
                                "engine.shed.shed_tier",
                                soc=round(soc, 0),
                                threshold=round(tier.shed_below_soc, 0),
                                tier=tier.name,
                            ),
                        )
                    )
            elif soc >= tier.restore_above_soc:
                if not tier.restore_enabled:
                    continue
                for entity in entities:
                    actions.append(
                        ShedAction(
                            tier=tier.name,
                            entity=entity,
                            desired_on=True,
                            reason=msg(
                                "engine.shed.restore_tier",
                                soc=round(soc, 0),
                                threshold=round(tier.restore_above_soc, 0),
                                tier=tier.name,
                            ),
                        )
                    )
        return actions

    def force_off_plan(self) -> list[ShedAction]:
        """Operator override: turn off every configured tier entity."""
        if not self._cfg.enabled or not self._cfg.tiers:
            return []

        actions: list[ShedAction] = []
        reason = msg("engine.override.force_shed_off")
        for tier in sorted(self._cfg.tiers, key=lambda t: t.priority):
            for entity in tier.entity_ids():
                actions.append(
                    ShedAction(
                        tier=tier.name,
                        entity=entity,
                        desired_on=False,
                        reason=reason,
                    )
                )
        return actions
