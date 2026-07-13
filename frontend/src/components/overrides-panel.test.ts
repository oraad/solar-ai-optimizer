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
    grid_charge_enabled: true,
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
    expect(root.textContent).toContain("Reserve pin requires an admin");
    expect(root.textContent).toContain("Load shedding");
    expect(root.textContent).toContain("Grid charge");
    expect(root.textContent).toContain("Optimization");
    expect(root.textContent).not.toContain("Pin reserve");
    expect(root.textContent).not.toContain("Run cycle now");
    expect(root.textContent).not.toContain("Clear overrides");
    expect(root.textContent).toContain("Kill switch");
    expect(root.textContent).toContain("Auto");
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
    el.remove();
  });

  it("hides grid charge row when disabled", async () => {
    const el = mountPanel("admin");
    el.status = {
      ...el.status!,
      grid_charge_enabled: false,
    };
    await el.updateComplete;
    const texts = buttonTexts(el);
    expect(texts.some((t) => t.includes("Force ON"))).toBe(false);
    el.remove();
  });

  it("viewer note does not claim grid-charge overrides are admin-only", async () => {
    const el = mountPanel("viewer");
    await el.updateComplete;
    expect(el.shadowRoot!.textContent).not.toContain("grid-charge overrides");
    el.remove();
  });

  it("shows forced grid charge banner when active", async () => {
    const el = mountPanel("viewer");
    el.status = {
      ...el.status!,
      force_grid_charge_override: true,
      paused_grid_charge: true,
    };
    await el.updateComplete;
    expect(el.shadowRoot!.textContent).toContain("forced on at max current");
    el.remove();
  });

  it("grid pause toggle shows Paused when forced", async () => {
    const el = mountPanel("viewer");
    el.status = {
      ...el.status!,
      force_grid_charge_override: true,
      paused_grid_charge: true,
    };
    await el.updateComplete;
    const gridRow = [...el.shadowRoot!.querySelectorAll(".ctrl")].find((row) =>
      row.textContent?.includes("Grid charge"),
    );
    expect(gridRow?.textContent).toContain("Paused");
    el.remove();
  });

  it("shows forced shed banner when active", async () => {
    const el = mountPanel("viewer");
    el.status = {
      ...el.status!,
      shedding_enabled: true,
      force_shed_off_override: true,
      paused_shedding: true,
    };
    await el.updateComplete;
    expect(el.shadowRoot!.textContent).toContain("forced off");
    el.remove();
  });

  it("shed pause toggle shows Paused when forced off", async () => {
    const el = mountPanel("viewer");
    el.status = {
      ...el.status!,
      shedding_enabled: true,
      force_shed_off_override: true,
      paused_shedding: true,
    };
    await el.updateComplete;
    const shedRow = [...el.shadowRoot!.querySelectorAll(".ctrl")].find((row) =>
      row.textContent?.includes("Load shedding"),
    );
    expect(shedRow?.textContent).toContain("Paused");
    expect(shedRow?.textContent).toContain("Force OFF");
    el.remove();
  });

  it("shows shed Auto, Paused, and Force OFF tri-state when shedding enabled", async () => {
    const el = mountPanel("viewer");
    el.status = {
      ...el.status!,
      shedding_enabled: true,
    };
    await el.updateComplete;
    const shedRow = [...el.shadowRoot!.querySelectorAll(".ctrl")].find((row) =>
      row.textContent?.includes("Load shedding"),
    );
    expect(shedRow?.querySelectorAll(".seg button").length).toBe(3);
    expect(shedRow?.textContent).toContain("Auto");
    expect(shedRow?.textContent).toContain("Paused");
    expect(shedRow?.textContent).toContain("Force OFF");
    el.remove();
  });

  it("running shed and optimization toggles use active good styling", async () => {
    const el = mountPanel("viewer");
    el.status = {
      ...el.status!,
      shedding_enabled: true,
      paused_shedding: false,
      force_shed_off_override: false,
      paused_grid_charge: false,
      paused_optimization: false,
    };
    await el.updateComplete;
    const rows = [...el.shadowRoot!.querySelectorAll(".ctrl")];
    const shedRow = rows.find((row) => row.textContent?.includes("Load shedding"));
    const optRow = rows.find((row) => row.textContent?.includes("Optimization"));
    const shedAutoBtn = shedRow?.querySelector(".seg button");
    const optBtn = optRow?.querySelector("button");
    expect(shedAutoBtn?.classList.contains("active")).toBe(true);
    expect(shedAutoBtn?.classList.contains("good")).toBe(true);
    expect(optBtn?.classList.contains("active")).toBe(true);
    expect(optBtn?.classList.contains("good")).toBe(true);
    el.remove();
  });
});
