import { beforeAll, describe, expect, it } from "vitest";

import { buildSubsystemAlerts } from "./subsystem-status.js";
import type { SystemStatus } from "./types.js";

beforeAll(async () => {
  await import("./locales/manifest.js");
});

function status(patch: Partial<SystemStatus> = {}): SystemStatus {
  return {
    telemetry: null,
    decision: null,
    grid_stats: null,
    ha_connected: true,
    telemetry_stale: false,
    telemetry_age_seconds: 1,
    forecast_misconfigured: false,
    forecast_degraded: false,
    engine_mode: "rules",
    engine_active: "rules",
    shadow_mode: true,
    paused: false,
    paused_shedding: false,
    paused_grid_charge: false,
    paused_optimization: false,
    shedding_enabled: true,
    grid_charge_enabled: true,
    engine_enabled: true,
    deployment_profile: "full",
    last_updated: new Date().toISOString(),
    ...patch,
  };
}

describe("buildSubsystemAlerts", () => {
  it("shows paused labels when subsystems are paused", () => {
    const alerts = buildSubsystemAlerts(
      status({ paused_shedding: true, paused_grid_charge: true, paused_optimization: true }),
    );
    expect(alerts.map((a) => a.className)).toEqual(["warn", "warn", "warn"]);
  });

  it("shows off labels when subsystems are disabled", () => {
    const alerts = buildSubsystemAlerts(
      status({ shedding_enabled: false, grid_charge_enabled: false, engine_enabled: false }),
    );
    expect(alerts.every((a) => a.className === "warn")).toBe(true);
  });

  it("shows GRID FORCED when force override is active", () => {
    const alerts = buildSubsystemAlerts(
      status({ force_grid_charge_override: true, paused_grid_charge: true }),
    );
    expect(alerts[1].label).toBe("GRID FORCED");
    expect(alerts[1].className).toBe("warn");
  });

  it("shows SHED FORCED when force shed off override is active", () => {
    const alerts = buildSubsystemAlerts(
      status({ force_shed_off_override: true, paused_shedding: true }),
    );
    expect(alerts[0].label).toBe("SHED FORCED");
    expect(alerts[0].className).toBe("warn");
  });
});
