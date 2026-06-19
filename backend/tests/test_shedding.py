"""Load shedding when SOC is unknown or telemetry is stale."""

from __future__ import annotations

from app.config import LoadSheddingConfig, LoadTier
from app.engine.shedding import LoadSheddingController
from app.models import Telemetry


def _ctrl(*, tiers: list[LoadTier] | None = None) -> LoadSheddingController:
    return LoadSheddingController(
        LoadSheddingConfig(
            enabled=True,
            tiers=tiers
            or [
                LoadTier(
                    name="pool",
                    switches=["switch.pool"],
                    shed_below_soc=40,
                    restore_above_soc=55,
                    priority=1,
                )
            ],
        )
    )


def test_unknown_soc_sheds_conservatively():
    ctrl = _ctrl()
    actions = ctrl.plan(Telemetry(battery_soc=None, grid_present=False))
    assert len(actions) == 1
    assert actions[0].desired_on is False


def test_stale_telemetry_sheds_conservatively():
    ctrl = _ctrl()
    actions = ctrl.plan(
        Telemetry(battery_soc=80.0, grid_present=False), telemetry_stale=True
    )
    assert len(actions) == 1
    assert actions[0].desired_on is False


def test_multi_switch_tier_emits_one_action_per_entity():
    ctrl = _ctrl(
        tiers=[
            LoadTier(
                name="pool",
                switches=["switch.pool_pump", "switch.pool_heater"],
                shed_below_soc=40,
                restore_above_soc=55,
                priority=1,
            )
        ]
    )
    actions = ctrl.plan(Telemetry(battery_soc=30.0, grid_present=False))
    assert len(actions) == 2
    assert {a.entity for a in actions} == {"switch.pool_pump", "switch.pool_heater"}
    assert all(a.desired_on is False for a in actions)
    assert all(a.tier == "pool" for a in actions)


def test_legacy_switch_field_loads_as_switches():
    tier = LoadTier.model_validate(
        {
            "name": "legacy",
            "switch": "switch.old",
            "shed_below_soc": 40,
            "restore_above_soc": 55,
        }
    )
    assert tier.switches == ["switch.old"]
    assert tier.entity_ids() == ["switch.old"]
