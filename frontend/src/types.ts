// Mirrors the backend Pydantic models (app/models.py).

export interface Telemetry {
  ts: string;
  pv_power: number | null;
  load_power: number | null;
  battery_soc: number | null;
  battery_power: number | null;
  grid_power: number | null;
  grid_present: boolean | null;
  battery_temp: number | null;
  outdoor_temp: number | null;
}

export interface ControlAction {
  capability: string;
  value: number | boolean;
  reason: string;
  priority: number;
}

export interface ReserveTarget {
  target_soc: number;
  solar_bridge_soc: number;
  autonomy_floor_soc: number;
  rationale: string;
}

export type BlackoutRisk = "low" | "moderate" | "high" | "critical";

export interface ShedAction {
  tier: string;
  entity: string;
  desired_on: boolean;
  reason: string;
}

export interface GridChargePlan {
  enabled: boolean;
  target_amps: number;
  max_amps: number;
  rationale: string;
}

export interface Decision {
  ts: string;
  reserve: ReserveTarget;
  actions: ControlAction[];
  shed_actions: ShedAction[];
  blackout_risk: BlackoutRisk;
  blackout_risk_score: number;
  summary: string;
  shadow_mode: boolean;
  grid_charge?: GridChargePlan | null;
}

export interface GridStats {
  uptime_pct_24h: number;
  uptime_pct_7d: number;
  avg_window_minutes: number;
  last_seen: string | null;
  currently_present: boolean | null;
  transitions_24h: number;
}

export interface ExecutionResult {
  capability: string;
  requested: number | boolean;
  applied: boolean;
  verified: boolean;
  skipped_reason: string | null;
  error: string | null;
  ts: string;
}

export interface ShedResult {
  tier: string;
  entity: string;
  desired_on: boolean;
  applied: boolean;
  verified: boolean;
  skipped_reason: string | null;
  error: string | null;
  ts: string;
}

export interface BatterySummary {
  capacity_kwh: number;
  round_trip_efficiency: number;
  max_soc_ceiling: number;
  min_soc_floor: number;
}

export interface SystemStatus {
  telemetry: Telemetry | null;
  decision: Decision | null;
  grid_stats: GridStats | null;
  battery_summary?: BatterySummary | null;
  ha_connected: boolean;
  telemetry_stale?: boolean;
  telemetry_age_seconds?: number | null;
  forecast_misconfigured?: boolean;
  forecast_degraded?: boolean;
  forecast_provider?: string;
  solcast_configured?: boolean;
  engine_mode?: string;
  engine_active?: string;
  mpc_available?: boolean;
  ml_available?: boolean;
  ml_load_enabled?: boolean;
  mpc_unavailable?: boolean;
  reserve_soc_override?: number | null;
  force_grid_charge_override?: boolean | null;
  shadow_mode: boolean;
  paused: boolean;
  last_updated: string;
}

export type AuthMode = "ingress" | "local" | "token" | "open" | "none";

export interface SessionInfo {
  authenticated: boolean;
  auth_mode: AuthMode;
  user_id: string | null;
  username: string | null;
  display_name: string | null;
  is_admin: boolean;
  login_required: boolean;
  version: string;
}

export interface DecisionHistoryRow {
  ts: string;
  target_soc: number;
  blackout_risk: BlackoutRisk;
  blackout_risk_score: number;
  shadow_mode: boolean;
  summary: string;
  reserve_rationale?: string;
  actions: ControlAction[];
  shed_actions: ShedAction[];
}

export interface GridEventRow {
  ts: string;
  grid_present: boolean;
}

export interface ExecutionHistoryRow {
  ts: string;
  capability: string;
  requested: string;
  applied: boolean;
  verified: boolean;
  skipped_reason: string | null;
  error: string | null;
}

export interface ShedExecutionRow {
  ts: string;
  tier: string;
  entity: string;
  desired_on: boolean;
  applied: boolean;
  verified: boolean;
  skipped_reason: string | null;
  error: string | null;
}

export interface SolarForecastPoint {
  ts: string;
  pv_power_w: number;
  pv_energy_wh: number;
}

export interface LoadForecastPoint {
  ts: string;
  load_power_w: number;
}

export interface TemperaturePoint {
  ts: string;
  temp_c: number;
}

export interface ForecastBundle {
  generated_at: string;
  solar: SolarForecastPoint[];
  load: LoadForecastPoint[];
  temperature: TemperaturePoint[];
  solar_today_kwh: number;
  solar_tomorrow_kwh: number;
  cloudy_tomorrow: boolean;
  heating_degree_hours_24h: number;
  cooling_degree_hours_24h: number;
  degraded?: boolean;
  degraded_reasons?: string[];
}

export interface Override {
  shadow_mode?: boolean | null;
  force_grid_charge?: boolean | null;
  reserve_soc?: number | null;
  pause_engine?: boolean | null;
  kill_switch?: boolean | null;
  /** Required when kill_switch is true (REST API). */
  confirm?: boolean;
}

export interface EntityInfo {
  entity_id: string;
  name: string;
  domain: string;
}

export interface AppConfigView {
  ha?: Record<string, unknown>;
  battery: Record<string, number>;
  reserve: Record<string, number>;
  forecast: Record<string, unknown>;
  control: Record<string, unknown>;
  fail_safe?: Record<string, unknown>;
  engine: Record<string, unknown>;
  inverter?: Record<string, unknown>;
  load_shedding?: Record<string, unknown>;
  grid_charge?: Record<string, unknown>;
}
