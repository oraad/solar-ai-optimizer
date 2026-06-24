import { beforeAll, describe, expect, it } from "vitest";

import type { EntityInput } from "./entity-input.js";
import type { EntityInfo } from "../types.js";

const ENTITIES: EntityInfo[] = [
  { entity_id: "sensor.battery_soc", name: "Battery SOC", domain: "sensor" },
  { entity_id: "switch.pool", name: "Pool pump", domain: "switch" },
  { entity_id: "input_boolean.guest", name: "Guest mode", domain: "input_boolean" },
];

beforeAll(async () => {
  await import("./entity-input.js");
});

function mountInput(domains: string[], entities = ENTITIES): EntityInput {
  const el = document.createElement("solar-entity-input") as EntityInput;
  el.entities = entities;
  el.domains = domains;
  document.body.appendChild(el);
  return el;
}

describe("EntityInput datalist", () => {
  it("renders a co-located datalist linked to the input for matching domains", async () => {
    const el = mountInput(["switch", "input_boolean"]);
    await el.updateComplete;

    const input = el.querySelector("input")!;
    const datalist = el.querySelector("datalist")!;
    expect(input.getAttribute("list")).toBe(datalist.id);
    expect(datalist.id).toMatch(/^dl-ei-/);

    const values = [...datalist.querySelectorAll("option")].map((o) => o.value);
    expect(values).toEqual(["switch.pool", "input_boolean.guest"]);

    el.remove();
  });

  it("omits list and datalist when no entities match domains", async () => {
    const el = mountInput(["climate"]);
    await el.updateComplete;

    const input = el.querySelector("input")!;
    expect(input.hasAttribute("list")).toBe(false);
    expect(el.querySelector("datalist")).toBeNull();

    el.remove();
  });

  it("assigns unique datalist ids per instance", async () => {
    const a = mountInput(["switch"]);
    const b = mountInput(["switch"]);
    await a.updateComplete;
    await b.updateComplete;

    const idA = a.querySelector("datalist")!.id;
    const idB = b.querySelector("datalist")!.id;
    expect(idA).not.toBe(idB);

    a.remove();
    b.remove();
  });
});
