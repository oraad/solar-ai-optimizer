import { describe, expect, it } from "vitest";

import { entityHelp, fieldHelp, overrideHelp, sectionHelp } from "./field-help.js";

describe("fieldHelp", () => {
  it("returns help for known settings", () => {
    expect(fieldHelp("reserve", "critical_load_w")).toContain("reserve");
    expect(fieldHelp("load_shedding", "shed_below_soc")).toContain("SOC");
    expect(fieldHelp("grid_charge", "battery_power")).toContain("charging");
  });

  it("returns undefined for unknown keys", () => {
    expect(fieldHelp("battery", "unknown_field")).toBeUndefined();
  });
});

describe("entityHelp", () => {
  it("returns help for inverter entities", () => {
    expect(entityHelp("battery_soc")).toContain("charge");
  });
});

describe("overrideHelp", () => {
  it("returns help for control actions", () => {
    expect(overrideHelp("kill_switch")).toContain("Emergency");
  });
});

describe("sectionHelp", () => {
  it("returns section summaries", () => {
    expect(sectionHelp("forecast")).toContain("solar");
    expect(sectionHelp("grid_charge")).toContain("lowest ceiling");
  });
});
