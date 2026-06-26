import { describe, expect, it } from "vitest";

import {
  buildSetupChecklist,
  checklistNeedsAttention,
  configSnapshot,
  isConfigDirty,
  validateConfigDraft,
} from "./settings-utils.js";
import type { AppConfigView } from "./types.js";

const baseConfig = (): AppConfigView => ({
  battery: { capacity_kwh: 10 },
  reserve: { critical_load_w: 400 },
  forecast: { provider: "open-meteo", arrays: [{ name: "a", kwp: 5, tilt: 15, azimuth: 180 }] },
  control: {},
  engine: { mode: "rules" },
  site: { latitude: -33.9, longitude: 18.4, timezone: "auto" },
  ha: { base_url: "http://ha", token: "", has_token: true, verify_ssl: true },
  inverter: {
    read: { pv_power: "s.pv", load_power: "s.load", battery_soc: "s.soc" },
    write: {},
  },
  fail_safe: {},
  grid_charge: { max_grid_charge_a: 60, min_grid_charge_a: 5 },
});

describe("settings-utils", () => {
  it("detects dirty draft after field change", () => {
    const cfg = baseConfig();
    const snap = configSnapshot(cfg);
    const draft = structuredClone(cfg);
    draft.site = { ...draft.site!, latitude: 0 };
    expect(isConfigDirty(draft, snap)).toBe(true);
    expect(isConfigDirty(cfg, snap)).toBe(false);
  });

  it("ignores HA token in dirty comparison", () => {
    const cfg = baseConfig();
    const snap = configSnapshot(cfg);
    const draft = structuredClone(cfg);
    draft.ha = { ...draft.ha!, token: "new-token" };
    expect(isConfigDirty(draft, snap)).toBe(false);
  });

  it("flags grid charge min > max", () => {
    const cfg = baseConfig();
    cfg.grid_charge = { max_grid_charge_a: 5, min_grid_charge_a: 60 };
    const issues = validateConfigDraft(cfg);
    expect(issues.some((i) => i.id === "grid_charge_min_max")).toBe(true);
  });

  it("builds checklist from status and draft", () => {
    const items = buildSetupChecklist(
      { forecast_misconfigured: false, ha_connected: true },
      baseConfig(),
      true,
    );
    expect(items.find((i) => i.id === "ha")?.done).toBe(true);
    expect(items.find((i) => i.id === "inverter")?.done).toBe(true);
    expect(checklistNeedsAttention(items)).toBe(false);
  });
});
