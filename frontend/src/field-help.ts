/** Short help text for settings fields, entities, and control actions. */



const FIELD_HELP: Record<string, Record<string, string>> = {

  battery: {

    capacity_kwh:

      "Usable battery energy capacity. Used for autonomy, reserve, and ETA calculations.",

    max_grid_charge_a:

      "Ceiling for grid charge current in amps. The ramp engine writes up to this value via the max grid charge current entity.",

    nominal_voltage:

      "Nominal pack voltage used to convert max grid charge current (amps) to watts in the MPC optimizer.",

    min_soc_floor:

      "Lowest SOC the optimizer will target or allow writes toward.",

    max_soc_ceiling:

      "Highest SOC cap used in planning, bound checks, and charge ETA.",

    round_trip_efficiency:

      "Round-trip efficiency (0–1). Accounts for losses when charging and discharging.",

  },

  reserve: {

    critical_load_w:

      "Minimum load that must stay powered (fridge, lights, comms). Drives reserve sizing.",

    min_autonomy_hours:

      "Hours of critical load the battery should cover without sun or grid.",

    solar_bridge_buffer_pct:

      "Extra SOC buffer while solar is expected soon, before dipping into the deep reserve.",

    cloudy_extra_buffer_pct:

      "Additional reserve buffer on overcast days when solar production is uncertain.",

  },

  forecast: {

    latitude: "Site latitude for solar and weather forecasts (decimal degrees).",

    longitude: "Site longitude for solar and weather forecasts (decimal degrees).",

    provider:

      "Solar forecast source: Open-Meteo (free) or Solcast (API key required via environment).",

    timezone: "IANA timezone for aligning forecasts, or auto from coordinates.",

    training_days:

      "Days of telemetry history used to train load bias and profile models.",

    min_load_fraction:

      "Floor on predicted load as a fraction of recent peak (avoids near-zero forecasts).",

  },

  control: {

    loop_interval_seconds:

      "How often the orchestrator reads telemetry and recomputes decisions.",

    forecast_interval_minutes: "How often solar/load forecasts are refreshed.",

    min_write_interval_seconds:

      "Minimum time between inverter writes to avoid spamming Home Assistant. When this exceeds the control loop interval, ramp steps may take multiple cycles to apply.",

    enforce_hard_bounds:

      "When enabled, reject grid charge current writes outside 0–max_grid_charge_a instead of silently clamping.",

    ha_stale_after_seconds:

      "Treat telemetry as stale after this many seconds without fresh HA updates.",

  },

  fail_safe: {

    heartbeat_entity:

      "input_datetime helper pulsed each control cycle (default: input_datetime.solar_optimizer_heartbeat from the HA fail-safe package).",

    heartbeat_enabled:

      "When enabled and an entity is set, pulse the heartbeat each control cycle.",

    shutdown_failsafe_enabled:

      "On graceful shutdown, enable grid charge at max current before exiting.",

  },

  load_shedding: {

    enabled: "Turn on automatic shedding of discretionary loads when SOC is low.",

    restore_all_when_grid_present:

      "When grid is detected, turn all shed tiers back on (battery no longer at risk).",

    name: "Logical name for this tier (shown in history and decision logs).",

    switches:

      "Home Assistant switch or input_boolean entities to turn off when shedding this tier.",

    shed_below_soc: "Turn entities off when battery SOC drops below this value.",

    restore_above_soc:

      "Turn entities back on when SOC rises above this value (hysteresis prevents flapping).",

    priority:

      "Shed order: lower numbers shed first; higher numbers are kept longer.",

  },

  grid_charge: {

    ramp_enabled:

      "When enabled, grid charge current ramps up/down using the factor cap chain below. When off, uses legacy max-or-off charging.",

    min_grid_charge_a:

      "Minimum amps when grid charge is enabled. If the cap chain yields a value below this (but above off threshold), it is bumped up to avoid flickering at very low currents.",

    ramp_step_a:

      "Maximum change in grid charge amps per control cycle.",

    off_threshold_a:

      "If the cap chain result is below this value, grid charge is disabled.",

    next_solar_horizon_hours:

      "Hours ahead to look for imminent solar when evaluating the next solar window factor.",

    soc_gap:

      "Maps SOC deficit vs reserve target to an urgency ceiling — larger gap allows higher current.",

    remaining_solar_today:

      "Lowers grid charge when forecast solar today can cover the energy needed to reach reserve.",

    next_solar_power:

      "Lowers grid charge when significant solar is expected in the next few hours.",

    load_power:

      "Adjusts ceiling based on net load minus PV — less import need allows lower current.",

    battery_power:

      "Reduces grid charge when the battery is already charging from solar (+ = charging).",

    grid_window:

      "Short historical grid windows raise urgency; long windows allow slower charging.",

    blackout_risk:

      "Higher blackout risk score allows a higher ceiling within the cap chain.",

    solar_bridge:

      "Larger gap between current SOC and solar-bridge target allows higher current.",

  },

  engine: {

    mode: "Rules: fast heuristics. MPC: optimization over the forecast horizon (needs PuLP). Charge and discharge power bounds both use max_grid_charge_a × nominal_voltage.",

    mpc_horizon_hours: "How many hours ahead the MPC engine plans when mode is MPC.",

  },

  ha: {

    base_url: "Home Assistant base URL, e.g. http://homeassistant.local:8123",

    token: "Long-lived access token with rights to read entities and call services.",

    verify_ssl:

      "Verify TLS certificates when connecting to Home Assistant over HTTPS.",

  },

  temperature: {

    enabled: "Model heating/cooling load from outdoor temperature in the forecast.",

    ha_entity:

      "Optional HA temperature sensor to bias-correct outdoor forecast readings.",

    hdd_base_c:

      "Heating degree-day base: outdoor temps below this add heating load.",

    cdd_base_c:

      "Cooling degree-day base: outdoor temps above this add cooling load.",

    use_month_fallback:

      "Use monthly average temperature when the outdoor sensor is unavailable.",

    min_load_fraction:

      "Minimum HVAC-related load as a fraction of the learned profile.",

    training_days: "Days of history used to fit the temperature load model.",

  },

  pv: {

    name: "Label for this PV array (informational; used in logs and UI).",

    kwp: "Peak DC capacity of the array in kilowatts-peak.",

    tilt: "Panel tilt from horizontal in degrees (0 = flat, 90 = vertical).",

    azimuth: "Compass direction panels face: 180° = south (northern hemisphere).",

  },

  security: {

    api_token:

      "Must match the server API_TOKEN. Stored only in this browser for authorized writes.",

  },

};



const ENTITY_HELP: Record<string, string> = {

  grid_present:

    "Binary sensor that is on when utility grid is connected to the inverter.",

  battery_soc: "Sensor reporting battery state of charge (%).",

  battery_voltage: "Battery voltage sensor used for validation and display.",

  battery_current: "Battery current sensor (charge/discharge sign per your inverter).",

  battery_power:

    "Battery power in watts (positive = charging). Enable “Invert battery power sign” in Settings if your inverter reports the opposite.",

  battery_temp: "Battery temperature for history charts and optional derating.",

  pv_power: "Total PV production power (W) from the inverter or meter.",

  load_power: "House load power (W) seen by the inverter or main meter.",

  grid_power: "Grid import/export power (W) if exposed by your integration.",

  grid_charge_enable:

    "Switch or select that enables grid charging on the inverter.",

  max_grid_charge_current:

    "Entity to limit current drawn from the grid for charging — the only charge-current write the optimizer uses.",

};



const PRIORITY_EFFECT_HELP: Record<string, string> = {

  resilience:

    "Higher rank: larger solar-bridge reserve buffers, stronger blackout-risk response, and more defensive planning when the grid is present.",

  savings:

    "Higher rank: more opportunistic grid charging when the grid is available and slightly leaner bridge buffers. Does not model electricity tariffs or time-of-use rates.",

  self_sufficiency:

    "Higher rank: stronger solar-trim factors in the grid-charge ramp and higher MPC penalty on curtailed PV — prefers using solar over grid top-up.",

};



const PRIORITY_RANK_BLURBS: Record<string, string> = {

  resilience: "defend reserve and outage survival",

  savings: "use grid opportunistically when present",

  self_sufficiency: "prefer solar over grid import",

};



const OVERRIDE_HELP: Record<string, string> = {

  mode:

    "Shadow logs decisions without writing to HA. Live applies inverter and shed commands.",

  engine:

    "Pause stops the control loop. Resume restarts automatic decisions.",

  grid_charge:

    "Force on enables grid charging regardless of the plan. Auto returns to optimizer control.",

  pin_reserve:

    "Override the computed target reserve SOC (%) until cleared or changed.",

  run_cycle: "Immediately run one decision cycle (forecast + plan + optional writes).",

  refresh_forecast: "Pull a fresh solar/load forecast without waiting for the scheduler.",

  clear_overrides:

    "Remove pause, reserve pin, force charge, and other temporary overrides.",

  kill_switch:

    "Emergency: enable grid charge at max current, pause engine, restore shed switches.",

};



const ASSISTANT_HELP: Record<string, string> = {

  apply:

    "When checked, parsed commands (reserve, pause, kill switch, etc.) are applied. Otherwise the assistant only explains.",

};



const STATUS_HELP: Record<string, string> = {

  solar: "Current PV production from your mapped sensor.",

  load: "House load power drawn from the inverter or main meter.",

  battery: "State of charge and charge/discharge power (+ = charging).",

  grid: "Whether utility grid is present and import/export power.",

  grid_charge: "Planned max grid charge current from the latest decision cycle.",

  reserve: "Target SOC the optimizer is defending right now.",

  risk: "Overall reserve risk level from the latest decision.",

  outdoor: "Outdoor temperature from forecast bias sensor or telemetry.",

};



function titleCaseSnake(key: string): string {

  return key

    .replace(/_/g, " ")

    .replace(/\b\w/g, (c) => c.toUpperCase());

}



export function fieldHelp(section: string, key: string): string | undefined {

  return FIELD_HELP[section]?.[key];

}



export function priorityEffectHelp(key: string): string | undefined {

  return PRIORITY_EFFECT_HELP[key];

}



export function priorityRankBlurb(key: string): string {

  return PRIORITY_RANK_BLURBS[key] ?? "";

}



export function entityHelp(key: string): string | undefined {

  return ENTITY_HELP[key];

}



export function pvHelp(key: string): string | undefined {

  return FIELD_HELP.pv[key];

}



export function overrideHelp(key: string): string | undefined {

  return OVERRIDE_HELP[key];

}



export function assistantHelp(key: string): string | undefined {

  return ASSISTANT_HELP[key];

}



export function statusHelp(key: string): string | undefined {

  return STATUS_HELP[key];

}



export function sectionHelp(section: string): string | undefined {

  const hints: Record<string, string> = {

    battery: "Physical battery limits used by forecasting and the decision engine.",

    reserve: "How much energy to hold back for outages and critical loads.",

    forecast: "Location, provider, and training settings for solar and load prediction.",

    control: "Timing and safety limits for the control loop and HA writes.",

    fail_safe:

      "Heartbeat for HA watchdog automation and grid-charge-at-max on shutdown.",

    load_shedding: "Optional tiers of switches to shed when SOC is low.",

    grid_charge:

      "Cap-chain factors that limit grid charge current each cycle (engine uses the lowest ceiling).",

    engine:

      "Rules vs MPC mode, plus reorderable optimization priorities (resilience, savings, self-sufficiency).",


    ha: "Connection settings for reading sensors and writing inverter controls.",

    inverter: "Map logical capabilities to your Home Assistant entity IDs.",

    pv_arrays: "Each array is forecast separately using tilt, azimuth, and peak power.",

    temperature: "Optional heating/cooling load model from outdoor temperature.",

  };

  return hints[section] ?? `Settings for ${titleCaseSnake(section)}.`;

}


