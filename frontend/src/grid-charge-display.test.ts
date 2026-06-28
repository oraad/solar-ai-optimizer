import { beforeEach, describe, expect, it } from "vitest";

import { gridChargeLabel, gridChargeSubline } from "./grid-charge-display.js";
import { initI18n, setLocale, t } from "./i18n.js";
import type { GridChargePlan } from "./types.js";

const plan = (overrides: Partial<GridChargePlan> = {}): GridChargePlan => ({
  enabled: true,
  target_amps: 32,
  max_amps: 60,
  rationale: "",
  ...overrides,
});

describe("gridChargeLabel", () => {
  beforeEach(async () => {
    localStorage.clear();
    await initI18n();
    await setLocale("en");
  });

  it("returns amps when enabled with target", () => {
    expect(gridChargeLabel(plan())).toBe("32 A");
  });

  it("returns off when disabled", () => {
    expect(gridChargeLabel(plan({ enabled: false, target_amps: 0 }))).toBe("OFF");
  });

  it("returns dash when no plan", () => {
    expect(gridChargeLabel(null)).toBe("--");
  });
});

describe("gridChargeSubline", () => {
  beforeEach(async () => {
    localStorage.clear();
    await initI18n();
    await setLocale("en");
  });

  it("returns null when grid charge subsystem disabled", () => {
    expect(gridChargeSubline(plan(), false, false)).toBeNull();
  });

  it("shows current and max when charging", () => {
    const sub = gridChargeSubline(plan(), false, true);
    expect(sub).toEqual({
      text: "32 A · max 60 A",
      color: "var(--good)",
    });
  });

  it("shows off and max when disabled", () => {
    const sub = gridChargeSubline(plan({ enabled: false, target_amps: 0 }), false, true);
    expect(sub).toEqual({
      text: "Off · max 60 A",
      color: "var(--muted)",
    });
  });

  it("shows off and max when grid absent (not Grid absent text)", () => {
    const sub = gridChargeSubline(plan(), true, true);
    expect(sub?.text).toBe("Off · max 60 A");
    expect(sub?.text).not.toContain("Grid absent");
    expect(sub?.color).toBe("var(--muted)");
  });

  it("shows off when grid absent even if plan says charging", () => {
    const sub = gridChargeSubline(plan({ enabled: true, target_amps: 40 }), true, true);
    expect(sub?.text).toBe("Off · max 60 A");
  });

  it("returns dash when no plan", () => {
    const sub = gridChargeSubline(null, false, true);
    expect(sub).toEqual({ text: "--", color: "var(--muted)" });
  });

  it("uses localized off string in label helper", () => {
    expect(t("common.off")).toBe("OFF");
  });
});
