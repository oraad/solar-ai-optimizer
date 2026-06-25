import { describe, expect, it } from "vitest";

import {
  filterEntitiesByDomains,
  hasEntitiesForDomains,
  SHED_DOMAINS,
  SHED_ENTITY_DOMAINS,
} from "./entity-datalists.js";
import type { EntityInfo } from "./types.js";

const ENTITIES: EntityInfo[] = [
  { entity_id: "sensor.battery_soc", name: "Battery SOC", domain: "sensor" },
  { entity_id: "switch.pool", name: "Pool pump", domain: "switch" },
  { entity_id: "input_boolean.guest", name: "Guest mode", domain: "input_boolean" },
];

describe("filterEntitiesByDomains", () => {
  it("filters to matching domains", () => {
    expect(filterEntitiesByDomains(ENTITIES, ["switch"])).toEqual([ENTITIES[1]]);
    expect(filterEntitiesByDomains(ENTITIES, [...SHED_ENTITY_DOMAINS])).toEqual([
      ENTITIES[1],
      ENTITIES[2],
    ]);
    expect(filterEntitiesByDomains(ENTITIES, SHED_DOMAINS)).toEqual([ENTITIES[1], ENTITIES[2]]);
  });

  it("returns empty when domains is empty", () => {
    expect(filterEntitiesByDomains(ENTITIES, [])).toEqual([]);
  });
});

describe("hasEntitiesForDomains", () => {
  it("is true when any entity matches", () => {
    expect(hasEntitiesForDomains(ENTITIES, ["switch"])).toBe(true);
    expect(hasEntitiesForDomains(ENTITIES, ["climate"])).toBe(false);
  });

  it("is false for empty domains", () => {
    expect(hasEntitiesForDomains(ENTITIES, [])).toBe(false);
  });
});
