"""Build decide-time DecisionExplanation (structured causality)."""

from __future__ import annotations

from ..models import (
    DecisionExplanation,
    DecisionModifiers,
    ExplanationStep,
    ForecastBundle,
    GridChargeExplanation,
    GridChargePlan,
    InputsDigest,
    ReserveExplanation,
    ReserveSource,
    ReserveTarget,
    RiskBreakdown,
    Telemetry,
)


def build_inputs_digest(
    telemetry: Telemetry,
    forecast: ForecastBundle | None,
    *,
    telemetry_stale: bool,
    plan_optimization: bool,
    plan_grid_charge: bool,
    plan_shedding: bool,
) -> InputsDigest:
    return InputsDigest(
        soc=telemetry.battery_soc,
        grid_present=telemetry.grid_present,
        telemetry_stale=telemetry_stale,
        forecast_degraded=bool(forecast and forecast.degraded),
        cloudy_tomorrow=bool(forecast and forecast.cloudy_tomorrow),
        solar_today_kwh=forecast.solar_today_kwh if forecast else None,
        solar_tomorrow_kwh=forecast.solar_tomorrow_kwh if forecast else None,
        plan_optimization=plan_optimization,
        plan_grid_charge=plan_grid_charge,
        plan_shedding=plan_shedding,
    )


def build_explanation(
    *,
    reserve: ReserveTarget,
    risk: RiskBreakdown,
    grid_charge: GridChargePlan | None,
    shed_count: int,
    modifiers: DecisionModifiers,
    inputs_digest: InputsDigest,
    mpc_soc: float | None = None,
    gc_mode: str = "",
) -> DecisionExplanation:
    steps: list[ExplanationStep] = []

    source = reserve.source
    steps.append(
        ExplanationStep(
            id="reserve",
            title_key="engine.explain.step.reserve",
            detail_key=_reserve_detail_key(source),
            params={
                "target": round(reserve.target_soc, 0),
                "source": source.value,
                "bridge": round(reserve.solar_bridge_soc, 0),
                "floor": round(reserve.autonomy_floor_soc, 0),
                "rules": round(reserve.rules_soc or reserve.target_soc, 0),
                "mpc": "" if mpc_soc is None else round(mpc_soc, 0),
            },
            outcome=f"{round(reserve.target_soc, 0)}%",
        )
    )

    if grid_charge is not None:
        binding = next((c for c in grid_charge.cap_chain if c.binding), None)
        steps.append(
            ExplanationStep(
                id="grid_charge",
                title_key="engine.explain.step.grid_charge",
                detail_key=(
                    "engine.explain.grid_charge.on"
                    if grid_charge.enabled
                    else "engine.explain.grid_charge.off"
                ),
                params={
                    "enabled": "yes" if grid_charge.enabled else "no",
                    "amps": round(grid_charge.target_amps, 1),
                    "binding": binding.factor if binding else "",
                    "ceiling": round(binding.ceiling_a, 0) if binding else "",
                    "mode": gc_mode,
                },
                outcome=(
                    f"{round(grid_charge.target_amps, 1)} A"
                    if grid_charge.enabled
                    else "off"
                ),
            )
        )

    steps.append(
        ExplanationStep(
            id="risk",
            title_key="engine.explain.step.risk",
            detail_key="engine.explain.risk.detail",
            params={
                "label": risk.label.value,
                "score": round(risk.score, 2),
                "deficit": (
                    ""
                    if risk.deficit_ratio is None
                    else round(risk.deficit_ratio, 2)
                ),
                "solar": (
                    "" if risk.solar_factor is None else round(risk.solar_factor, 2)
                ),
            },
            outcome=risk.label.value,
        )
    )

    reserve_x = ReserveExplanation(
        source=source,
        rules_soc=reserve.rules_soc,
        mpc_soc=mpc_soc,
        applied_soc=reserve.target_soc,
        solar_bridge_soc=reserve.solar_bridge_soc,
        autonomy_floor_soc=reserve.autonomy_floor_soc,
        driver=(
            "solar_bridge"
            if reserve.solar_bridge_soc >= reserve.autonomy_floor_soc
            else "autonomy_floor"
        ),
    )

    gc_x = GridChargeExplanation()
    if grid_charge is not None:
        binding = next((c for c in grid_charge.cap_chain if c.binding), None)
        gc_x = GridChargeExplanation(
            enabled=grid_charge.enabled,
            target_amps=grid_charge.target_amps,
            binding_factor=binding.factor if binding else None,
            binding_ceiling_a=binding.ceiling_a if binding else None,
            mode=gc_mode,
        )

    return DecisionExplanation(
        schema_version=1,
        steps=steps[:5],
        reserve=reserve_x,
        risk=risk,
        grid_charge=gc_x,
        shed_count=shed_count,
        modifiers=modifiers,
        inputs_digest=inputs_digest,
    )


def _reserve_detail_key(source: ReserveSource) -> str:
    if source == ReserveSource.MPC:
        return "engine.explain.reserve.mpc"
    if source == ReserveSource.OPERATOR:
        return "engine.explain.reserve.operator"
    return "engine.explain.reserve.rules"
