import { beforeAll, describe, expect, it } from "vitest";

import type { LoadSheddingPanel } from "./load-shedding-panel.js";
import type { AppConfigView, EntityInfo } from "../types.js";

const ENTITIES: EntityInfo[] = [
  { entity_id: "switch.pool", name: "Pool pump", domain: "switch" },
  { entity_id: "input_boolean.guest", name: "Guest mode", domain: "input_boolean" },
];

const TIER_CONFIG = {
  enabled: true,
  restore_all_when_grid_present: true,
  tiers: [
    {
      name: "pool",
      switches: [""],
      shed_below_soc: 40,
      restore_above_soc: 55,
      priority: 0,
      restore_enabled: true,
      restore_on_grid: true,
      state_entities: {},
    },
  ],
};

const TIER_WITH_COMPANIONS = {
  ...TIER_CONFIG,
  tiers: [
    {
      ...TIER_CONFIG.tiers[0],
      switches: ["switch.pool"],
      state_entities: { "switch.pool": ["climate.pool_heater"] },
    },
  ],
};

beforeAll(async () => {
  await import("./entity-input.js");
  await import("./info-tip.js");
  await import("./load-shedding-panel.js");
});

function mountPanelInShadow(
  entities = ENTITIES,
  config = TIER_CONFIG,
): { host: HTMLElement; panel: LoadSheddingPanel } {
  const host = document.createElement("div");
  host.attachShadow({ mode: "open" });
  const panel = document.createElement("solar-load-shedding-panel") as LoadSheddingPanel;
  panel.config = { load_shedding: config } as unknown as AppConfigView;
  panel.entities = entities;
  panel.entitiesConnected = true;
  host.shadowRoot!.appendChild(panel);
  document.body.appendChild(host);
  return { host, panel };
}

describe("LoadSheddingPanel collapse defaults", () => {
  async function waitForTiers(panel: LoadSheddingPanel): Promise<void> {
    await panel.updateComplete;
    await new Promise((r) => setTimeout(r, 0));
    await panel.updateComplete;
  }

  it("renders tier blocks collapsed with summary metadata", async () => {
    const { host, panel } = mountPanelInShadow();
    await waitForTiers(panel);

    const tierBlock = panel.shadowRoot!.querySelector(".tier-block") as HTMLDetailsElement;
    expect(tierBlock).toBeTruthy();
    expect(tierBlock.open).toBe(false);

    const summary = tierBlock.querySelector(".tier-summary-text")!;
    expect(summary.textContent).toContain("pool");
    expect(summary.textContent).toContain("Shed 40%");
    expect(summary.textContent).toContain("Priority 0");
    expect(summary.textContent).toContain("0 devices");

    host.remove();
  });

  it("keeps companion sections collapsed when companions exist", async () => {
    const { host, panel } = mountPanelInShadow(ENTITIES, TIER_WITH_COMPANIONS);
    await waitForTiers(panel);

    const companionDetails = panel.shadowRoot!.querySelector(
      ".companion-details",
    ) as HTMLDetailsElement;
    expect(companionDetails).toBeTruthy();
    expect(companionDetails.open).toBe(false);

    host.remove();
  });
});

describe("LoadSheddingPanel entity autocomplete", () => {
  it("renders tier entity inputs with shed-domain datalists inside shadow DOM", async () => {
    const { host, panel } = mountPanelInShadow();
    await panel.updateComplete;
    await new Promise((r) => setTimeout(r, 0));

    const tierBlock = panel.shadowRoot!.querySelector(".tier-block") as HTMLDetailsElement;
    tierBlock.open = true;
    await panel.updateComplete;

    const entityInput = panel.shadowRoot!.querySelector("solar-entity-input")!;
    expect(entityInput).toBeTruthy();
    await (entityInput as HTMLElement & { updateComplete: Promise<unknown> }).updateComplete;

    const input = entityInput.shadowRoot!.querySelector("input")!;
    const datalist = entityInput.shadowRoot!.querySelector("datalist")!;
    expect(input.getAttribute("list")).toBe(datalist.id);

    const values = [...datalist.querySelectorAll("option")].map((o) => o.value);
    expect(values).toEqual(["switch.pool", "input_boolean.guest"]);

    host.remove();
  });
});
