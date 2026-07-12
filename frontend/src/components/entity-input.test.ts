import { beforeAll, describe, expect, it } from "vitest";

import type { EntityInput } from "./entity-input.js";
import type { EntityInfo } from "../types.js";

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
    expect(values).toEqual(["switch.pool", "input_boolean.guest"]);

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

  it("filters input_datetime and sets option label to friendly name", async () => {
    const el = mountInput(["input_datetime"]);
    await el.updateComplete;

    const opts = [...root(el).querySelectorAll("option")];
    expect(opts).toHaveLength(1);
    expect(opts[0]!.value).toBe("input_datetime.solar_optimizer_heartbeat");
    expect(opts[0]!.getAttribute("label")).toBe("Solar optimizer heartbeat");
    expect(opts[0]!.textContent).toBe("Solar optimizer heartbeat");

    el.entityId = "input_datetime.solar_optimizer_heartbeat";
    el.requestUpdate();
    await el.updateComplete;
    expect(root(el).querySelector("input")!.value).toBe("Solar optimizer heartbeat");

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
    expect(values).toEqual(["switch.pool", "input_boolean.guest"]);

    host.remove();
  });
});
