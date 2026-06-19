import { describe, expect, it } from "vitest";

import { entityDisplayName, resolveEntity } from "./entity-resolve.js";
import type { EntityInfo } from "./types.js";

const ENTITIES: EntityInfo[] = [
  { entity_id: "sensor.battery_soc", name: "Battery SOC", domain: "sensor" },
  { entity_id: "switch.pool", name: "Pool pump", domain: "switch" },
  { entity_id: "input_boolean.guest", name: "Guest mode", domain: "input_boolean" },
  { entity_id: "sensor.duplicate", name: "Living room", domain: "sensor" },
  { entity_id: "sensor.duplicate2", name: "Living room", domain: "sensor" },
];

describe("entityDisplayName", () => {
  it("returns friendly name when known", () => {
    expect(entityDisplayName("sensor.battery_soc", ENTITIES)).toBe("Battery SOC");
  });

  it("falls back to raw id", () => {
    expect(entityDisplayName("sensor.unknown", ENTITIES)).toBe("sensor.unknown");
  });
});

describe("resolveEntity", () => {
  it("resolves by exact entity_id", () => {
    expect(resolveEntity("sensor.battery_soc", ENTITIES)).toBe("sensor.battery_soc");
  });

  it("resolves by unique friendly name", () => {
    expect(resolveEntity("Pool pump", ENTITIES)).toBe("switch.pool");
  });

  it("accepts manually typed domain.entity", () => {
    expect(resolveEntity("sensor.custom_foo", ENTITIES)).toBe("sensor.custom_foo");
  });

  it("returns null for ambiguous name", () => {
    expect(resolveEntity("Living room", ENTITIES)).toBeNull();
  });

  it("returns null for empty", () => {
    expect(resolveEntity("  ", ENTITIES)).toBeNull();
  });

  it("respects domain filter", () => {
    expect(resolveEntity("Pool pump", ENTITIES, ["switch"])).toBe("switch.pool");
    expect(resolveEntity("Pool pump", ENTITIES, ["sensor"])).toBeNull();
  });
});
