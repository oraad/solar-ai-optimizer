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


def test_restore_disabled_skips_soc_restore():
    ctrl = _ctrl(
        tiers=[
            LoadTier(
                name="pool",
                switches=["switch.pool"],
                shed_below_soc=40,
                restore_above_soc=55,
                restore_enabled=False,
                priority=1,
            )
        ]
    )
    actions = ctrl.plan(Telemetry(battery_soc=80.0, grid_present=False))
    assert actions == []


def test_restore_on_grid_disabled_skips_grid_restore():
    ctrl = _ctrl(
        tiers=[
            LoadTier(
                name="pool",
                switches=["switch.pool"],
                shed_below_soc=40,
                restore_above_soc=55,
                restore_on_grid=False,
                priority=1,
            )
        ]
    )
    actions = ctrl.plan(Telemetry(battery_soc=30.0, grid_present=True))
    assert actions == []


def test_companions_for_autodiscover_when_key_missing():
    tier = LoadTier(name="t", switches=["switch.a"])
    assert tier.companions_for("switch.a") is None


def test_companions_for_empty_list_when_explicit():
    tier = LoadTier(
        name="t",
        switches=["switch.a"],
        state_entities={"switch.a": []},
    )
    assert tier.companions_for("switch.a") == []


def test_force_off_plan_turns_off_all_tier_entities():
    ctrl = _ctrl(
        tiers=[
            LoadTier(
                name="pool",
                switches=["switch.pool_pump", "switch.pool_heater"],
                shed_below_soc=40,
                restore_above_soc=55,
                priority=1,
            ),
            LoadTier(
                name="ac",
                switches=["switch.ac"],
                shed_below_soc=30,
                restore_above_soc=50,
                priority=2,
            ),
        ]
    )
    actions = ctrl.force_off_plan()
    assert len(actions) == 3
    assert {a.entity for a in actions} == {
        "switch.pool_pump",
        "switch.pool_heater",
        "switch.ac",
    }
    assert all(a.desired_on is False for a in actions)


def test_soc_restore_only_when_pending():
    ctrl = _ctrl()
    tel = Telemetry(battery_soc=80.0, grid_present=False)
    assert ctrl.plan(tel, pending_restore=set()) == []
    actions = ctrl.plan(tel, pending_restore={"switch.pool"})
    assert len(actions) == 1
    assert actions[0].desired_on is True
    assert actions[0].entity == "switch.pool"


def test_grid_restore_only_when_pending():
    ctrl = _ctrl()
    tel = Telemetry(battery_soc=30.0, grid_present=True)
    assert ctrl.plan(tel, pending_restore=set()) == []
    actions = ctrl.plan(tel, pending_restore={"switch.pool"})
    assert len(actions) == 1
    assert actions[0].desired_on is True
    assert actions[0].entity == "switch.pool"


def test_shed_below_ignores_pending_restore():
    ctrl = _ctrl()
    actions = ctrl.plan(
        Telemetry(battery_soc=30.0, grid_present=False),
        pending_restore=set(),
    )
    assert len(actions) == 1
    assert actions[0].desired_on is False
