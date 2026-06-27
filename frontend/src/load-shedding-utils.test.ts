import { describe, expect, it } from "vitest";

import {
  normalizeTiersForSave,
  tierDeviceCount,
  tierSwitches,
  validateLoadSheddingTiers,
} from "./load-shedding-utils.js";

describe("load-shedding-utils", () => {
  it("tierSwitches prefers switches array over legacy switch", () => {
    expect(tierSwitches({ switches: ["switch.a", "switch.b"] })).toEqual(["switch.a", "switch.b"]);
    expect(tierSwitches({ switch: "switch.legacy" })).toEqual(["switch.legacy"]);
    expect(tierSwitches({})).toEqual([""]);
  });

  it("tierDeviceCount ignores blank entries", () => {
    expect(tierDeviceCount({ switches: ["switch.a", ""] })).toBe(1);
  });

  it("validateLoadSheddingTiers requires name and entities", () => {
    const msg = (key: string, params?: Record<string, string>) =>
      params ? `${key}:${JSON.stringify(params)}` : key;
    expect(validateLoadSheddingTiers({ tiers: [{ name: "", switches: ["switch.a"] }] }, msg)).toContain(
      "validationTierName",
    );
    expect(
      validateLoadSheddingTiers({ tiers: [{ name: "pool", switches: [""] }] }, msg),
    ).toContain("validationTierEntities");
    expect(validateLoadSheddingTiers({ tiers: [{ name: "pool", switches: ["switch.a"] }] }, msg)).toBeNull();
  });

  it("normalizeTiersForSave migrates legacy switch field", () => {
    const d = { tiers: [{ name: "pool", switch: "switch.pool", priority: 0 }] };
    normalizeTiersForSave(d);
    expect(d.tiers[0]).toMatchObject({ switches: ["switch.pool"], priority: 0 });
    expect(d.tiers[0]).not.toHaveProperty("switch");
  });
});
