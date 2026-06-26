import { describe, expect, it } from "vitest";

import {
  groupShedActionsByTier,
  groupShedResultsByTier,
  shedActionTooltip,
  shedResultTooltip,
} from "./shed-display.js";
import type { ShedAction, ShedResult } from "./types.js";

function shedAction(overrides: Partial<ShedAction> & Pick<ShedAction, "tier" | "entity">): ShedAction {
  return {
    desired_on: false,
    reason: "shed reason",
    ...overrides,
  };
}

function shedResult(overrides: Partial<ShedResult> & Pick<ShedResult, "tier" | "entity">): ShedResult {
  return {
    desired_on: false,
    applied: false,
    verified: false,
    skipped_reason: null,
    error: null,
    ts: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("groupShedActionsByTier", () => {
  it("collapses multiple entities in the same tier", () => {
    const actions = [
      shedAction({ tier: "pool", entity: "switch.a", reason: "low soc" }),
      shedAction({ tier: "pool", entity: "switch.b", reason: "low soc" }),
      shedAction({ tier: "pool", entity: "switch.c", reason: "low soc" }),
    ];
    const grouped = groupShedActionsByTier(actions);
    expect(grouped).toHaveLength(1);
    expect(grouped[0].tier).toBe("pool");
    expect(grouped[0].entities).toEqual(["switch.a", "switch.b", "switch.c"]);
    expect(grouped[0].reason).toBe("low soc");
  });

  it("preserves first-seen tier order", () => {
    const actions = [
      shedAction({ tier: "hvac", entity: "switch.hvac" }),
      shedAction({ tier: "pool", entity: "switch.pool" }),
      shedAction({ tier: "hvac", entity: "switch.fan" }),
    ];
    const grouped = groupShedActionsByTier(actions);
    expect(grouped.map((g) => g.tier)).toEqual(["hvac", "pool"]);
    expect(grouped[0].entities).toEqual(["switch.hvac", "switch.fan"]);
  });
});

describe("shedActionTooltip", () => {
  it("includes reason and per-entity state lines", () => {
    const summary = groupShedActionsByTier([
      shedAction({ tier: "pool", entity: "switch.a", desired_on: false }),
      shedAction({ tier: "pool", entity: "switch.b", desired_on: false }),
    ])[0];
    const tip = shedActionTooltip(summary, "ON", "SHED");
    expect(tip).toBe("shed reason\nswitch.a: SHED\nswitch.b: SHED");
  });
});

describe("groupShedResultsByTier", () => {
  it("reports all verified when every entity succeeded", () => {
    const results = [
      shedResult({ tier: "pool", entity: "switch.a", verified: true }),
      shedResult({ tier: "pool", entity: "switch.b", verified: true }),
    ];
    const grouped = groupShedResultsByTier(results);
    expect(grouped).toHaveLength(1);
    expect(grouped[0].allVerified).toBe(true);
    expect(grouped[0].uniformSkipReason).toBeNull();
  });

  it("detects uniform skip reason across entities", () => {
    const results = [
      shedResult({
        tier: "pool",
        entity: "switch.a",
        skipped_reason: "engine.skip.shadow_mode",
        skipped_reason_text: "Shadow mode",
      }),
      shedResult({
        tier: "pool",
        entity: "switch.b",
        skipped_reason: "engine.skip.shadow_mode",
        skipped_reason_text: "Shadow mode",
      }),
    ];
    const grouped = groupShedResultsByTier(results);
    expect(grouped[0].allVerified).toBe(false);
    expect(grouped[0].uniformSkipReason).toBe("engine.skip.shadow_mode");
    expect(grouped[0].uniformSkipReasonText).toBe("Shadow mode");
    expect(grouped[0].hasPartialFailure).toBe(false);
  });

  it("flags partial failure when outcomes differ", () => {
    const results = [
      shedResult({ tier: "pool", entity: "switch.a", verified: true }),
      shedResult({
        tier: "pool",
        entity: "switch.b",
        skipped_reason: "engine.skip.ha_stale",
        skipped_reason_text: "HA stale",
      }),
    ];
    const grouped = groupShedResultsByTier(results);
    expect(grouped[0].hasPartialFailure).toBe(true);
    expect(grouped[0].uniformSkipReason).toBeNull();
    expect(grouped[0].primarySkipReasonText).toBe("HA stale");
  });

  it("merges companions and wasOffBeforeShed across entities", () => {
    const results = [
      shedResult({
        tier: "pool",
        entity: "switch.a",
        companions_restored: ["climate.heater"],
      }),
      shedResult({
        tier: "pool",
        entity: "switch.b",
        skipped_reason: "engine.skip.was_off_before_shed",
        companions_restored: ["input_boolean.guest"],
      }),
    ];
    const grouped = groupShedResultsByTier(results);
    expect(grouped[0].wasOffBeforeShed).toBe(true);
    expect(grouped[0].companionsRestored).toEqual(["climate.heater", "input_boolean.guest"]);
  });
});

describe("shedResultTooltip", () => {
  it("lists per-entity execution status", () => {
    const grouped = groupShedResultsByTier([
      shedResult({ tier: "pool", entity: "switch.a", verified: true, desired_on: false }),
      shedResult({
        tier: "pool",
        entity: "switch.b",
        skipped_reason: "engine.skip.ha_stale",
        skipped_reason_text: "HA stale",
      }),
    ]);
    const tip = shedResultTooltip(grouped[0]);
    expect(tip).toBe("switch.a: off ok\nswitch.b: off HA stale");
  });
});
