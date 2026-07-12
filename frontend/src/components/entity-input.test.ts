import { beforeAll, describe, expect, it } from "vitest";

import type { EntityInput } from "./entity-input.js";
import { datalistOptionValue } from "./entity-input.js";
import type { EntityInfo } from "../types.js";
import { resolveEntity } from "../entity-resolve.js";

const ENTITIES: EntityInfo[] = [
  { entity_id: "sensor.battery_soc", name: "Battery SOC", domain: "sensor" },
  { entity_id: "switch.pool", name: "Pool pump", domain: "switch" },
  { entity_id: "input_boolean.guest", name: "Guest mode", domain: "input_boolean" },
  {
    entity_id: "input_datetime.solar_optimizer_heartbeat",
    name: "Solar optimizer heartbeat",
    domain: "input_datetime",
  },
];

beforeAll(async () => {
  await import("./entity-input.js");
});

function root(el: EntityInput): ShadowRoot {
  return el.shadowRoot!;
}

function mountInput(domains: string[], entities = ENTITIES): EntityInput {
  const el = document.createElement("solar-entity-input") as EntityInput;
  el.entities = entities;
  el.domains = domains;
  document.body.appendChild(el);
  return el;
}

describe("datalistOptionValue", () => {
  it("uses friendly name when unique", () => {
    expect(datalistOptionValue(ENTITIES[3]!, ENTITIES)).toBe("Solar optimizer heartbeat");
  });

  it("falls back to entity_id when names collide", () => {
    const peers: EntityInfo[] = [
      { entity_id: "input_datetime.a", name: "Heartbeat", domain: "input_datetime" },
      { entity_id: "input_datetime.b", name: "Heartbeat", domain: "input_datetime" },
    ];
    expect(datalistOptionValue(peers[0]!, peers)).toBe("input_datetime.a");
    expect(datalistOptionValue(peers[1]!, peers)).toBe("input_datetime.b");
  });
});

describe("EntityInput datalist", () => {
  it("renders a co-located datalist linked to the input for matching domains", async () => {
    const el = mountInput(["switch", "input_boolean"]);
    await el.updateComplete;

    const input = root(el).querySelector("input")!;
    const datalist = root(el).querySelector("datalist")!;
    expect(input.getAttribute("list")).toBe(datalist.id);
    expect(datalist.id).toMatch(/^dl-ei-/);
    expect(input.getAttribute("autocomplete")).toBe("off");

    const values = [...datalist.querySelectorAll("option")].map((o) => o.value);
    expect(values).toEqual(["Pool pump", "Guest mode"]);

    el.remove();
  });

  it("omits list and datalist when no entities match domains", async () => {
    const el = mountInput(["climate"]);
    await el.updateComplete;

    const input = root(el).querySelector("input")!;
    expect(input.hasAttribute("list")).toBe(false);
    expect(root(el).querySelector("datalist")).toBeNull();

    el.remove();
  });

  it("filters input_datetime and uses friendly name as option value", async () => {
    const el = mountInput(["input_datetime"]);
    await el.updateComplete;

    const opts = [...root(el).querySelectorAll("option")];
    expect(opts).toHaveLength(1);
    expect(opts[0]!.value).toBe("Solar optimizer heartbeat");
    expect(opts[0]!.textContent).toBe("input_datetime.solar_optimizer_heartbeat");

    el.entityId = "input_datetime.solar_optimizer_heartbeat";
    el.requestUpdate();
    await el.updateComplete;
    expect(root(el).querySelector("input")!.value).toBe("Solar optimizer heartbeat");

    expect(
      resolveEntity("Solar optimizer heartbeat", ENTITIES, ["input_datetime"]),
    ).toBe("input_datetime.solar_optimizer_heartbeat");

    el.remove();
  });

  it("uses entity_id option values when friendly names collide", async () => {
    const peers: EntityInfo[] = [
      { entity_id: "input_datetime.a", name: "Heartbeat", domain: "input_datetime" },
      { entity_id: "input_datetime.b", name: "Heartbeat", domain: "input_datetime" },
    ];
    const el = mountInput(["input_datetime"], peers);
    await el.updateComplete;
    const values = [...root(el).querySelectorAll("option")].map((o) => o.value);
    expect(values).toEqual(["input_datetime.a", "input_datetime.b"]);
    el.remove();
  });

  it("assigns unique datalist ids per instance", async () => {
    const a = mountInput(["switch"]);
    const b = mountInput(["switch"]);
    await a.updateComplete;
    await b.updateComplete;

    const idA = root(a).querySelector("datalist")!.id;
    const idB = root(b).querySelector("datalist")!.id;
    expect(idA).not.toBe(idB);

    a.remove();
    b.remove();
  });

  it("renders datalist when mounted inside a parent shadow root", async () => {
    const host = document.createElement("div");
    host.attachShadow({ mode: "open" });
    const el = document.createElement("solar-entity-input") as EntityInput;
    el.entities = ENTITIES;
    el.domains = ["switch", "input_boolean"];
    host.shadowRoot!.appendChild(el);
    document.body.appendChild(host);
    await el.updateComplete;

    const input = root(el).querySelector("input")!;
    const datalist = root(el).querySelector("datalist")!;
    expect(input.getAttribute("list")).toBe(datalist.id);
    const values = [...datalist.querySelectorAll("option")].map((o) => o.value);
    expect(values).toEqual(["Pool pump", "Guest mode"]);

    host.remove();
  });
});
