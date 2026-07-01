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

function buttonTexts(el: OverridesPanel): string[] {
  return [...el.shadowRoot!.querySelectorAll<HTMLButtonElement>("button")].map(
    (b) => b.textContent?.trim() ?? "",
  );
}

describe("OverridesPanel role", () => {
  it("viewer mode shows operator controls and hides admin actions", async () => {
    const el = mountPanel("viewer");
    await el.updateComplete;
    const root = el.shadowRoot!;
    expect(root.textContent).toContain("Operator controls");
    expect(root.textContent).toContain("require an admin");
    expect(root.textContent).toContain("Load shedding");
    expect(root.textContent).toContain("Grid charge");
    expect(root.textContent).toContain("Optimization");
    expect(root.textContent).not.toContain("Pin reserve");
    expect(root.textContent).not.toContain("Run cycle now");
    expect(root.textContent).not.toContain("Clear overrides");
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

  it("shows Resume all when engine fully paused", async () => {
    const el = mountPanel("admin");
    el.status = {
      ...el.status!,
      paused: true,
      paused_shedding: true,
      paused_grid_charge: true,
      paused_optimization: true,
    };
    await el.updateComplete;
    const texts = buttonTexts(el);
    expect(texts.some((t) => t.includes("Resume all"))).toBe(true);
    expect(texts.some((t) => t.includes("Pause all"))).toBe(false);
    el.remove();
  });

  it("viewer shows Resume all when engine fully paused", async () => {
    const el = mountPanel("viewer");
    el.status = {
      ...el.status!,
      paused: true,
      paused_shedding: true,
      paused_grid_charge: true,
      paused_optimization: true,
    };
    await el.updateComplete;
    const texts = buttonTexts(el);
    expect(texts.some((t) => t.includes("Resume all"))).toBe(true);
    expect(texts.some((t) => t.includes("Pause all"))).toBe(false);
    el.remove();
  });

  it("shows Resume all and Pause all on partial pause", async () => {
    const el = mountPanel("viewer");
    el.status = {
      ...el.status!,
      paused: false,
      paused_shedding: true,
      paused_grid_charge: false,
      paused_optimization: false,
    };
    await el.updateComplete;
    const texts = buttonTexts(el);
    expect(texts.some((t) => t.includes("Resume all"))).toBe(true);
    expect(texts.some((t) => t.includes("Pause all"))).toBe(true);
    el.remove();
  });

  it("shows only Pause all when nothing paused", async () => {
    const el = mountPanel("viewer");
    await el.updateComplete;
    const texts = buttonTexts(el);
    expect(texts.some((t) => t.includes("Pause all"))).toBe(true);
    expect(texts.some((t) => t.includes("Resume all"))).toBe(false);
    el.remove();
  });

  it("viewer subsystem toggle shows Paused when paused", async () => {
    const el = mountPanel("viewer");
    el.status = {
      ...el.status!,
      paused_shedding: true,
    };
    await el.updateComplete;
    expect(el.shadowRoot!.textContent).toContain("Paused");
    const shedButton = [...el.shadowRoot!.querySelectorAll<HTMLButtonElement>("button")].find(
      (b) => b.textContent?.includes("Paused"),
    );
    expect(shedButton?.disabled).toBe(false);
    el.remove();
  });

  it("admin mode hides grid charge when disabled", async () => {
    const el = mountPanel("admin");
    el.status = {
      ...el.status!,
      grid_charge_enabled: false,
    };
    await el.updateComplete;
    expect(el.shadowRoot!.textContent).not.toContain("Force on");
    el.remove();
  });
});
