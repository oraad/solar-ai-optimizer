import { describe, expect, it } from "vitest";

import { batteryEtaLine, formatDuration } from "./duration.js";

describe("formatDuration", () => {
  it("formats sub-hour durations", () => {
    expect(formatDuration(45)).toBe("45m");
  });

  it("formats hours and minutes", () => {
    expect(formatDuration(135)).toBe("2h 15m");
  });

  it("caps at 24h", () => {
    expect(formatDuration(2000)).toBe(">24h");
  });

  it("hides very short durations", () => {
    expect(formatDuration(1)).toBe("");
  });
});

describe("batteryEtaLine", () => {
  const base = {
    soc: 50,
    capacityKwh: 10,
    roundTripEfficiency: 0.9,
    maxSocCeiling: 100,
    minSocFloor: 20,
    targetSoc: 80,
    autonomyFloorSoc: 30,
  };

  it("shows charge ETA", () => {
    const line = batteryEtaLine({ ...base, powerW: 2000 });
    expect(line).toMatch(/^Full in ~/);
  });

  it("shows discharge ETA", () => {
    const line = batteryEtaLine({ ...base, powerW: -1500 });
    expect(line).toMatch(/^Reserve in ~/);
  });

  it("hides when idle", () => {
    expect(batteryEtaLine({ ...base, powerW: 5 })).toBeNull();
  });
});
