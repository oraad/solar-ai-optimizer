import { beforeAll, describe, expect, it } from "vitest";

import type { OverridesPanel } from "./overrides-panel.js";

beforeAll(async () => {
  await import("./overrides-panel.js");
});

function mountPanel(role: "admin" | "viewer"): OverridesPanel {
  const el = document.createElement("solar-overrides-panel") as OverridesPanel;
  el.role = role;
  el.status = {
    telemetry: null,
    decision: null,
    grid_stats: null,
    ha_connected: true,
    shadow_mode: true,
    paused: false,
    last_updated: new Date().toISOString(),
  };
  document.body.appendChild(el);
  return el;
}

describe("OverridesPanel role", () => {
  it("viewer mode shows operator controls and hides admin actions", async () => {
    const el = mountPanel("viewer");
    await el.updateComplete;
    const root = el.shadowRoot!;
    expect(root.textContent).toContain("Operator controls");
    expect(root.textContent).toContain("require an admin");
    expect(root.textContent).not.toContain("Pin reserve");
    expect(root.textContent).not.toContain("Run cycle now");
    expect(root.textContent).toContain("Kill switch");
    el.remove();
  });

  it("admin mode shows full override panel", async () => {
    const el = mountPanel("admin");
    await el.updateComplete;
    const root = el.shadowRoot!;
    expect(root.textContent).toMatch(/Controls.*overrides/);
    expect(root.textContent).toContain("Pin reserve");
    expect(root.textContent).toContain("Run cycle now");
    expect(root.textContent).toContain("Clear overrides");
    el.remove();
  });

  it("shows resume action when engine already paused", async () => {
    const el = mountPanel("admin");
    el.status = {
      ...el.status!,
      paused: true,
    };
    await el.updateComplete;
    const buttons = [...el.shadowRoot!.querySelectorAll<HTMLButtonElement>("button")];
    const resume = buttons.find((b) => b.textContent?.includes("Resume"));
    expect(resume).toBeTruthy();
    expect(resume?.disabled).toBe(false);
    el.remove();
  });
});
