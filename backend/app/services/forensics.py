"""Decision forensics: assemble inputs, reasoning, and execution gaps for debugging."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..engine.priorities import resolve_weights
from ..i18n.serialize import localize_model, localize_payload
from ..observability.capabilities import ml_available, mpc_available
from ..observability.metrics import metrics
from .config_view import config_view

if TYPE_CHECKING:
    from ..orchestrator import Orchestrator

DEFAULT_SECTIONS = frozenset({"inputs", "engine", "overrides", "decision", "execution", "ops"})
ALL_SECTIONS = DEFAULT_SECTIONS | frozenset({"config"})


def _parse_sections(sections: str | None) -> frozenset[str]:
    if not sections or sections.strip().lower() == "all":
        return ALL_SECTIONS
    parts = {p.strip().lower() for p in sections.split(",") if p.strip()}
    return parts & ALL_SECTIONS if parts else DEFAULT_SECTIONS


def build_decision_trace(orch: Orchestrator, *, sections: str | None = None) -> dict:
    """Assemble a troubleshooting bundle from live orchestrator state."""
    wanted = _parse_sections(sections)
    trace: dict = {}

    if "inputs" in wanted:
        telemetry = orch.collector.latest
        forecast = orch.forecast.current
        trace["inputs"] = {
            "telemetry": (
                telemetry.model_dump(mode="json") if telemetry else None
            ),
            "telemetry_stale": orch._telemetry_stale(telemetry) if telemetry else True,
            "telemetry_age_seconds": orch._telemetry_age_seconds(),
            "forecast": (
                forecast.model_dump(mode="json") if forecast else None
            ),
            "grid_stats": (
                orch.latest_grid_stats.model_dump(mode="json")
                if orch.latest_grid_stats
                else None
            ),
        }

    if "engine" in wanted:
        plan_opt, plan_gc, plan_shed = orch._plan_flags()
        weights = resolve_weights(orch.cfg.engine.priority_order)
        trace["engine"] = {
            "mode": orch.cfg.engine.mode,
            "active": "mpc" if orch._mpc is not None else "rules",
            "mpc_available": mpc_available(),
            "ml_available": ml_available(),
            "mpc_unavailable": orch.cfg.engine.mode == "mpc" and orch._mpc is None,
            "priority_order": [p.value for p in orch.cfg.engine.priority_order],
            "priority_weights": {k.value: v for k, v in weights.items()},
            "plan_optimization": plan_opt,
            "plan_grid_charge": plan_gc,
            "plan_shedding": plan_shed,
            "engine_enabled": orch.cfg.engine.enabled,
            "grid_charge_enabled": orch.cfg.grid_charge.enabled,
            "shedding_enabled": orch.cfg.load_shedding.enabled,
        }

    if "overrides" in wanted:
        trace["overrides"] = {
            "shadow_mode": orch.shadow_mode,
            "paused": orch.paused,
            "paused_shedding": orch.paused_shedding,
            "paused_grid_charge": orch.paused_grid_charge,
            "paused_optimization": orch.paused_optimization,
            "override": orch.override.model_dump(mode="json"),
        }

    if "decision" in wanted:
        decision = orch.latest_decision
        trace["decision"] = localize_model(decision) if decision else None

    if "execution" in wanted:
        trace["execution"] = {
            "results": localize_payload(
                [r.model_dump(mode="json") for r in orch.latest_results]
            ),
            "shed_results": localize_payload(
                [r.model_dump(mode="json") for r in orch.latest_shed_results]
            ),
            "shadow_mode": orch.shadow_mode,
        }

    if "ops" in wanted:
        trace["ops"] = {
            "metrics": metrics.as_dict(),
            "note": "Read-only snapshot; simulate does not mutate these counters.",
        }

    if "config" in wanted:
        trace["config"] = config_view(orch.cfg)

    return redact_trace(trace)


def redact_trace(trace: dict) -> dict:
    """Ensure no secrets appear in forensics payloads."""
    cfg = trace.get("config")
    if isinstance(cfg, dict):
        ha = cfg.get("ha")
        if isinstance(ha, dict):
            ha["token"] = ""
    return trace


def build_simulate_response(orch: Orchestrator, decision) -> dict:  # noqa: ANN001
    """Trace + hypothetical decision; documents race with live control cycle."""
    base = build_decision_trace(orch, sections="all")
    base["hypothetical_decision"] = (
        localize_model(decision) if decision else None
    )
    base["simulate_note"] = (
        "Dry-run using cached telemetry/forecast; does not apply writes or "
        "persist decisions. May race with an in-flight control cycle."
    )
    return base
