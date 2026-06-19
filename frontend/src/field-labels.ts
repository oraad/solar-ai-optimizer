/** Human-readable labels for Settings fields (display only; keys unchanged in API). */



const SECTION_TITLES: Record<string, string> = {

  battery: "Battery",

  reserve: "Reserve",

  forecast: "Forecast",

  control: "Control",

  fail_safe: "Fail-safe",

  load_shedding: "Load shedding",

  engine: "Engine",

  ha: "Home Assistant",

  inverter: "Inverter",

};



const FIELD_LABELS: Record<string, Record<string, string>> = {

  battery: {

    capacity_kwh: "Capacity (kWh)",

    max_charge_a: "Max charge current (A)",

    max_grid_charge_a: "Max grid charge current (A)",

    nominal_voltage: "Nominal voltage (V)",

    min_soc_floor: "Minimum SOC floor (%)",

    max_soc_ceiling: "Maximum SOC ceiling (%)",

    round_trip_efficiency: "Round-trip efficiency",

  },

  reserve: {

    critical_load_w: "Critical load (W)",

    min_autonomy_hours: "Min autonomy (hours)",

    solar_bridge_buffer_pct: "Solar bridge buffer (%)",

    cloudy_extra_buffer_pct: "Cloudy extra buffer (%)",

  },

  forecast: {

    latitude: "Latitude",

    longitude: "Longitude",

    provider: "Solar forecast provider",

    timezone: "Timezone",

    training_days: "Training history (days)",

    min_load_fraction: "Minimum load fraction",

  },

  control: {

    loop_interval_seconds: "Control loop interval (s)",

    forecast_interval_minutes: "Forecast interval (min)",

    min_write_interval_seconds: "Min write interval (s)",

    enforce_hard_bounds: "Enforce hard bounds",

    ha_stale_after_seconds: "HA stale timeout (s)",

  },

  fail_safe: {

    heartbeat_entity: "Heartbeat entity",

    heartbeat_enabled: "Heartbeat enabled",

    shutdown_failsafe_enabled: "Shutdown fail-safe enabled",

  },

  load_shedding: {

    enabled: "Load shedding enabled",

    restore_all_when_grid_present: "Restore all tiers when grid present",

    name: "Tier name",

    switches: "Shed entities",

    shed_below_soc: "Shed below SOC (%)",

    restore_above_soc: "Restore above SOC (%)",

    priority: "Priority",

  },

  engine: {

    mode: "Engine mode",

    mpc_horizon_hours: "MPC horizon (hours)",

  },

  ha: {

    base_url: "Home Assistant URL",

    token: "Access token",

    verify_ssl: "Verify SSL certificate",

  },

  temperature: {

    enabled: "Temperature load model enabled",

    ha_entity: "Outdoor temperature sensor (°C)",

    hdd_base_c: "Heating base temperature (°C)",

    cdd_base_c: "Cooling base temperature (°C)",

    use_month_fallback: "Use monthly fallback when sensor missing",

    min_load_fraction: "Minimum load fraction",

    training_days: "Training history (days)",

  },

  pv: {

    name: "Array name",

    kwp: "Peak power (kWp)",

    tilt: "Tilt (°)",

    azimuth: "Azimuth (°)",

  },

};



const ENTITY_LABELS: Record<string, string> = {

  grid_present: "Grid present sensor",

  battery_soc: "Battery state of charge (%)",

  battery_voltage: "Battery voltage (V)",

  battery_current: "Battery current (A)",

  battery_power: "Battery power (W)",

  battery_temp: "Battery temperature (°C)",

  pv_power: "PV power (W)",

  load_power: "Load power (W)",

  grid_power: "Grid power (W)",

  grid_charge_enable: "Grid charge enable",

  max_grid_charge_current: "Max grid charge current (A)",

  work_mode: "Work mode",

};



function titleCaseSnake(key: string): string {

  return key

    .replace(/_/g, " ")

    .replace(/\b\w/g, (c) => c.toUpperCase());

}



export function sectionTitle(section: string): string {

  return SECTION_TITLES[section] ?? titleCaseSnake(section);

}



export function fieldLabel(section: string, key: string): string {

  return FIELD_LABELS[section]?.[key] ?? titleCaseSnake(key);

}



export function entityLabel(key: string): string {

  return ENTITY_LABELS[key] ?? titleCaseSnake(key);

}



export function pvLabel(key: string): string {

  return FIELD_LABELS.pv[key] ?? titleCaseSnake(key);

}



/** Read-map entity keys rendered in Settings (excludes non-entity flags). */

export const INVERTER_READ_ENTITY_KEYS = [

  "pv_power",

  "load_power",

  "battery_soc",

  "battery_power",

  "grid_power",

  "grid_present",

  "battery_temp",

] as const;


