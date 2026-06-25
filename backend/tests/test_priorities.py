"""Optimization priority resolver and scale helpers."""

from __future__ import annotations

import pytest

from app.config import EngineConfig, OptimizationPriority
from app.engine.priorities import (
    BlendMode,
    buffer_scale,
    blend_ceiling,
    grid_present_risk_multiplier,
    mpc_weights,
    resolve_weights,
    savings_buffer_relief,
)
from app.grid.ramp import RampContext, compute_ramp_plan
from app.config import BatteryConfig, GridChargeConfig, GridChargeFactor, ReserveConfig
from app.models import BlackoutRisk, GridStats, ReserveTarget, Telemetry
from tests.conftest import DUMMY_MSG


def test_engine_config_rejects_invalid_priority_order():
    with pytest.raises(ValueError, match="priority_order"):
        EngineConfig(priority_order=["resilience", "resilience", "savings"])


def test_resolve_weights_default_order():
    w = resolve_weights()
    assert w[OptimizationPriority.resilience] == 1.0
    assert w[OptimizationPriority.savings] == 0.4
    assert w[OptimizationPriority.self_sufficiency] == 0.15


def test_golden_default_scales_are_identity():
    w = resolve_weights()
    assert buffer_scale(w[OptimizationPriority.resilience]) == 1.0
    assert savings_buffer_relief(w[OptimizationPriority.savings]) == 1.0
    assert grid_present_risk_multiplier(
        w[OptimizationPriority.resilience],
        w[OptimizationPriority.savings],
    ) == pytest.approx(0.5)
    w_res, w_cur = mpc_weights(w)
    assert w_res == pytest.approx(1000.0)
    assert w_cur == pytest.approx(1.0)


def test_buffer_scale_clamped():
    assert buffer_scale(0.15) == pytest.approx(0.90)
    assert buffer_scale(1.0) == pytest.approx(1.0)


def test_savings_relief_only_when_ranked_high():
    assert savings_buffer_relief(0.4) == 1.0
    assert savings_buffer_relief(0.15) == 1.0
    assert savings_buffer_relief(1.0) == pytest.approx(0.92)


def test_mpc_weights_self_sufficiency_first():
    order = [
        OptimizationPriority.self_sufficiency,
        OptimizationPriority.resilience,
        OptimizationPriority.savings,
    ]
    w_res, w_cur = mpc_weights(resolve_weights(order))
    assert w_cur > 1.0
    assert w_res / w_cur >= 100.0


def test_blend_ceiling_default_scale_is_identity():
    max_a = 60.0
    raw = 24.0
    for mode, priority in (
        (BlendMode.TRIM, OptimizationPriority.self_sufficiency),
        (BlendMode.URGENCY, OptimizationPriority.resilience),
        (BlendMode.SAVINGS, OptimizationPriority.savings),
    ):
        w = resolve_weights()[priority]
        assert blend_ceiling(raw, max_a, w, mode, priority) == pytest.approx(raw)


def test_blend_ceiling_savings_relaxes_when_ranked_higher():
    max_a = 60.0
    raw = 24.0
    loose = blend_ceiling(
        raw, max_a, 1.0, BlendMode.SAVINGS, OptimizationPriority.savings
    )
    tight = blend_ceiling(
        raw, max_a, resolve_weights()[OptimizationPriority.savings],
        BlendMode.SAVINGS,
        OptimizationPriority.savings,
    )
    assert loose > tight
    assert loose == pytest.approx(max_a)


def test_blend_ceiling_trim_strengthens_when_resilience_promoted():
    max_a = 60.0
    raw = 20.0
    strong = blend_ceiling(
        raw, max_a, 1.0, BlendMode.TRIM, OptimizationPriority.self_sufficiency
    )
    weak = blend_ceiling(
        raw,
        max_a,
        resolve_weights()[OptimizationPriority.self_sufficiency],
        BlendMode.TRIM,
        OptimizationPriority.self_sufficiency,
    )
    assert strong <= weak
    assert strong == pytest.approx(raw)
    demoted = blend_ceiling(
        raw, max_a, 0.15, BlendMode.URGENCY, OptimizationPriority.resilience
    )
    promoted = blend_ceiling(
        raw, max_a, 1.0, BlendMode.URGENCY, OptimizationPriority.resilience
    )
    assert promoted < demoted


def test_savings_first_raises_grid_window_ceiling():
    battery = BatteryConfig()
    grid_charge = GridChargeConfig(
        max_grid_charge_a=60.0,
        factor_order=[GridChargeFactor.grid_window],
    )
    reserve = ReserveTarget(
        target_soc=55.0,
        solar_bridge_soc=55.0,
        autonomy_floor_soc=30.0,
        rationale=DUMMY_MSG,
    )
    base = dict(
        telemetry=Telemetry(battery_soc=40.0, grid_present=True),
        forecast=None,
        grid_stats=GridStats(avg_window_minutes=200.0),
        reserve=reserve,
        target_soc=55.0,
        blackout_risk=BlackoutRisk.LOW,
        blackout_risk_score=0.2,
        battery=battery,
        grid_charge=grid_charge,
    )
    ctx_default = RampContext(
        **base,
        priority_weights={
            k.value: v
            for k, v in resolve_weights(
                [
                    OptimizationPriority.resilience,
                    OptimizationPriority.savings,
                    OptimizationPriority.self_sufficiency,
                ]
            ).items()
        },
    )
    ctx_savings_first = RampContext(
        **base,
        priority_weights={
            k.value: v
            for k, v in resolve_weights(
                [
                    OptimizationPriority.savings,
                    OptimizationPriority.resilience,
                    OptimizationPriority.self_sufficiency,
                ]
            ).items()
        },
    )
    plan_default = compute_ramp_plan(ctx_default)
    plan_savings = compute_ramp_plan(ctx_savings_first)
    assert plan_savings.target_amps >= plan_default.target_amps
