"""Domain models shared across the app (telemetry, plans, forecasts)."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


def new_cycle_id() -> str:
    return str(uuid4())


class Msg(BaseModel):
    """Localized message stored as a catalog key + interpolation params."""

    key: str
    params: dict[str, str | int | float] = Field(default_factory=dict)

    def text(self, locale: str | None = None) -> str:
        if not self.key:
            return ""
        from .i18n import t

        return t(self.key, self.params, locale=locale)  # type: ignore[arg-type]

    def __str__(self) -> str:
        return self.text()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """Normalize DB-loaded timestamps (SQLite returns naive UTC) for comparisons."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class Telemetry(BaseModel):
    """A single snapshot of inverter/home state."""

    ts: datetime = Field(default_factory=utcnow)
    pv_power: float | None = None          # W
    load_power: float | None = None        # W
    battery_soc: float | None = None       # %
    battery_power: float | None = None     # W (+charge / -discharge)
    grid_power: float | None = None        # W
    grid_present: bool | None = None
    battery_temp: float | None = None      # degC
    outdoor_temp: float | None = None      # degC (optional HA outdoor sensor)


class Capability(str, Enum):
    """Logical write capabilities the engine may target.

    Active values: grid_charge_enable, max_grid_charge_current.
    Execution history stores capability as plain strings and may include
    removed values (e.g. work_mode, legacy min_soc).
    """

    GRID_CHARGE_ENABLE = "grid_charge_enable"
    MAX_GRID_CHARGE_CURRENT = "max_grid_charge_current"


class ControlAction(BaseModel):
    """A single desired write, with the reasoning behind it."""

    capability: Capability
    value: float | bool
    reason: Msg
    priority: int = 0  # higher = more important


class ShedAction(BaseModel):
    """A desired on/off state for a sheddable load tier (HA switch)."""

    tier: str
    entity: str
    desired_on: bool
    reason: Msg


class ShedResult(BaseModel):
    tier: str
    entity: str
    desired_on: bool
    applied: bool
    verified: bool
    skipped_reason: str | None = None
    error: str | None = None
    companions_captured: list[str] = Field(default_factory=list)
    companions_restored: list[str] = Field(default_factory=list)
    companion_errors: dict[str, str] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=utcnow)
    cycle_id: str | None = None


class GridEvent(BaseModel):
    """A grid on/off transition (display-only stats; never used for prediction)."""

    ts: datetime = Field(default_factory=utcnow)
    grid_present: bool


class GridStats(BaseModel):
    """Grid statistics for display and charge-window planning."""

    uptime_pct_24h: float = 0.0
    uptime_pct_7d: float = 0.0
    avg_window_minutes: float = 0.0
    last_seen: datetime | None = None
    currently_present: bool | None = None
    transitions_24h: int = 0
    present_elapsed_minutes: float | None = None
    remaining_window_minutes: float | None = None


class SolarForecastPoint(BaseModel):
    ts: datetime
    pv_power_w: float        # forecast instantaneous PV power
    pv_energy_wh: float = 0  # energy in the step


class LoadForecastPoint(BaseModel):
    ts: datetime
    load_power_w: float


class TemperaturePoint(BaseModel):
    ts: datetime
    temp_c: float


class ForecastBundle(BaseModel):
    generated_at: datetime = Field(default_factory=utcnow)
    solar: list[SolarForecastPoint] = Field(default_factory=list)
    load: list[LoadForecastPoint] = Field(default_factory=list)
    temperature: list[TemperaturePoint] = Field(default_factory=list)
    solar_today_kwh: float = 0.0
    solar_tomorrow_kwh: float = 0.0
    cloudy_tomorrow: bool = False
    heating_degree_hours_24h: float = 0.0
    cooling_degree_hours_24h: float = 0.0
    degraded: bool = False
    degraded_reasons: list[Msg] = Field(default_factory=list)


class ReserveSource(str, Enum):
    RULES = "rules"
    MPC = "mpc"
    OPERATOR = "operator"


class ReserveTarget(BaseModel):
    """The computed conservative battery floor and its drivers."""

    target_soc: float                # % we want to defend
    solar_bridge_soc: float          # % from the solar-bridge calc
    autonomy_floor_soc: float        # % from the hard autonomy floor
    rationale: Msg
    source: ReserveSource = ReserveSource.RULES
    rules_soc: float | None = None   # pre-pin rules target when source != rules
    effective_critical_w: float | None = None
    smoothed_load_w: float | None = None
    smoothed_discharge_w: float | None = None
    adaptive_blend_a: float | None = None


class CapChainFactor(BaseModel):
    """One factor in the grid-charge amp cap chain."""

    factor: str
    ceiling_a: float
    note_key: str = ""
    note_params: dict[str, str | int | float] = Field(default_factory=dict)
    binding: bool = False


class GridChargePlan(BaseModel):
    """Planned grid charge for one decision cycle."""

    enabled: bool
    target_amps: float
    max_amps: float
    rationale: Msg = Field(default_factory=lambda: Msg(key=""))
    cap_chain: list[CapChainFactor] = Field(default_factory=list)


class BlackoutRisk(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class ExplanationStep(BaseModel):
    """One ordered causal step for the Decision Story."""

    id: str
    title_key: str
    detail_key: str = ""
    params: dict[str, str | int | float] = Field(default_factory=dict)
    outcome: str = ""  # e.g. applied target, amps, risk label


class RiskBreakdown(BaseModel):
    score: float = 0.0
    label: BlackoutRisk = BlackoutRisk.LOW
    deficit_ratio: float | None = None
    solar_factor: float | None = None
    tomorrow_kwh: float | None = None
    clear_sky_kwh: float | None = None
    grid_multiplier: float | None = None
    floor_clamped: bool = False


class ReserveExplanation(BaseModel):
    source: ReserveSource = ReserveSource.RULES
    rules_soc: float | None = None
    mpc_soc: float | None = None
    applied_soc: float | None = None
    solar_bridge_soc: float | None = None
    autonomy_floor_soc: float | None = None
    driver: str = ""
    effective_critical_w: float | None = None
    smoothed_load_w: float | None = None
    smoothed_discharge_w: float | None = None
    adaptive_blend_a: float | None = None

class GridChargeExplanation(BaseModel):
    enabled: bool = False
    target_amps: float = 0.0
    binding_factor: str | None = None
    binding_ceiling_a: float | None = None
    mode: str = ""  # ramp | legacy | override | off | stale


class DecisionModifiers(BaseModel):
    shadow: bool = True
    paused_writes_grid: bool = False
    paused_writes_shed: bool = False
    paused_optimization: bool = False
    force_grid_charge: bool | None = None
    force_shed_off: bool | None = None
    reserve_pin: float | None = None
    engine_active: str = "rules"


class InputsDigest(BaseModel):
    """Compact decide-time inputs for provenance (not a full telemetry dump)."""

    soc: float | None = None
    grid_present: bool | None = None
    telemetry_stale: bool = False
    forecast_degraded: bool = False
    cloudy_tomorrow: bool = False
    solar_today_kwh: float | None = None
    solar_tomorrow_kwh: float | None = None
    plan_optimization: bool = True
    plan_grid_charge: bool = True
    plan_shedding: bool = True


class DecisionExplanation(BaseModel):
    """Decide-time structured causality (schema_version for forward compat)."""

    schema_version: int = 1
    steps: list[ExplanationStep] = Field(default_factory=list)
    reserve: ReserveExplanation = Field(default_factory=ReserveExplanation)
    risk: RiskBreakdown = Field(default_factory=RiskBreakdown)
    grid_charge: GridChargeExplanation = Field(default_factory=GridChargeExplanation)
    shed_count: int = 0
    modifiers: DecisionModifiers = Field(default_factory=DecisionModifiers)
    inputs_digest: InputsDigest = Field(default_factory=InputsDigest)


class ExecutionSummary(BaseModel):
    """Post-execute verification summary (never mutates Decision.explanation)."""

    cycle_id: str | None = None
    grid_charge_writes_allowed: bool = False
    shedding_writes_allowed: bool = False
    applied: int = 0
    verified: int = 0
    skipped: int = 0
    errors: int = 0
    top_skip_keys: list[str] = Field(default_factory=list)
    shed_applied: int = 0
    shed_skipped: int = 0
    intended_reserve_soc: float | None = None
    intended_grid_charge_amps: float | None = None
    applied_grid_charge_amps: float | None = None
    grid_charge_status: str = ""  # applied|verified|skipped|paused|shadow|none


class Decision(BaseModel):
    """The engine's output for one cycle."""

    ts: datetime = Field(default_factory=utcnow)
    cycle_id: str = Field(default_factory=new_cycle_id)
    reserve: ReserveTarget
    actions: list[ControlAction] = Field(default_factory=list)
    shed_actions: list[ShedAction] = Field(default_factory=list)
    blackout_risk: BlackoutRisk = BlackoutRisk.LOW
    blackout_risk_score: float = 0.0  # 0..1
    summary: Msg = Field(default_factory=lambda: Msg(key=""))
    shadow_mode: bool = True
    grid_charge: GridChargePlan | None = None
    explanation: DecisionExplanation | None = None
    slim: bool = False  # True when history row is header-only


class ExecutionResult(BaseModel):
    """Outcome of attempting to apply a single action."""

    capability: Capability
    requested: float | bool
    applied: bool
    verified: bool
    skipped_reason: str | None = None
    error: str | None = None
    ts: datetime = Field(default_factory=utcnow)
    cycle_id: str | None = None


class BatterySummary(BaseModel):
    """Non-secret battery specs for dashboard ETA (included in live status)."""

    capacity_kwh: float
    round_trip_efficiency: float
    max_soc_ceiling: float
    min_soc_floor: float


class SystemStatus(BaseModel):
    """Aggregated live status surfaced to the dashboard."""

    telemetry: Telemetry | None = None
    decision: Decision | None = None
    execution_summary: ExecutionSummary | None = None
    grid_stats: GridStats | None = None
    battery_summary: BatterySummary | None = None
    ha_connected: bool = False
    telemetry_stale: bool = False
    telemetry_age_seconds: float | None = None
    forecast_misconfigured: bool = False
    forecast_degraded: bool = False
    forecast_provider: str = "open-meteo"
    solcast_configured: bool = False
    engine_mode: str = "rules"
    engine_active: str = "rules"
    mpc_available: bool = False
    ml_available: bool = False
    ml_load_enabled: bool = False
    mpc_unavailable: bool = False
    reserve_soc_override: float | None = None
    force_grid_charge_override: bool | None = None
    force_shed_off_override: bool | None = None
    shadow_mode: bool = True
    paused: bool = False
    shedding_enabled: bool = False
    grid_charge_enabled: bool = True
    engine_enabled: bool = True
    paused_shedding: bool = False
    paused_grid_charge: bool = False
    paused_optimization: bool = False
    grid_charge_writes_available: bool = False
    deployment_profile: str = "full"
    timezone_config: str = "auto"
    timezone_resolved: str | None = None
    last_updated: datetime = Field(default_factory=utcnow)


class Override(BaseModel):
    """A manual operator override sent from the dashboard."""

    shadow_mode: bool | None = None
    force_grid_charge: bool | None = None
    force_shed_off: bool | None = None
    reserve_soc: float | None = None     # pin reserve target (None = auto)
    pause_engine: bool | None = None
    pause_shedding: bool | None = None
    pause_grid_charge: bool | None = None
    pause_optimization: bool | None = None
    kill_switch: bool | None = None      # grid charge at max; pause engine (orchestrator)
