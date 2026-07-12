import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { INPUT_DATETIME_DOMAINS } from "../entity-datalists.js";
import type { SettingsPanel } from "./settings-panel.js";

beforeAll(async () => {
  class MockIntersectionObserver {
    observe() {}
    disconnect() {}
    unobserve() {}
  }
  vi.stubGlobal("IntersectionObserver", MockIntersectionObserver);
  await import("./settings-panel.js");
});

function mountPanel(overrides: Partial<SettingsPanel> = {}): SettingsPanel {
  const el = document.createElement("solar-settings-panel") as SettingsPanel;
  el.config = {
    site: { latitude: 0, longitude: 0 },
    battery: {},
    reserve: {},
    forecast: {},
    control: {},
    engine: {},
    inverter: { read: {}, write: {} },
    ha: { base_url: "http://ha.local", has_token: false },
    fail_safe: {},
    grid_charge: {},
  } as SettingsPanel["config"];
  el.session = { role: "admin", auth_mode: "none", is_addon: false } as unknown as SettingsPanel["session"];
  Object.assign(el, overrides);
  document.body.appendChild(el);
  return el;
}

describe("SettingsPanel MCP section", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("renders disabled MCP pill when health reports mcp disabled", async () => {
    const el = mountPanel();
    (el as unknown as { layoutWide: boolean }).layoutWide = true;
    (el as unknown as { mcpHealth: unknown }).mcpHealth = {
      status: "ok",
      mcp_enabled: false,
      mcp_auth_configured: false,
      mcp_http_mounted: false,
    };
    el.requestUpdate();
    await el.updateComplete;
    expect(el.shadowRoot!.textContent).toContain("Disabled");
    el.remove();
  });

  it("shows misconfigured warning when enabled without auth", async () => {
    const el = mountPanel();
    (el as unknown as { layoutWide: boolean }).layoutWide = true;
    (el as unknown as { mcpHealth: unknown }).mcpHealth = {
      status: "ok",
      mcp_enabled: true,
      mcp_auth_configured: false,
      mcp_http_mounted: false,
    };
    el.requestUpdate();
    await el.updateComplete;
    expect(el.shadowRoot!.querySelector('[role="alert"]')).not.toBeNull();
    el.remove();
  });

  it("shows HA add-on note instead of env table on addon session", async () => {
    const el = mountPanel();
    (el as unknown as { layoutWide: boolean }).layoutWide = true;
    el.session = { role: "admin", auth_mode: "none", is_addon: true } as unknown as SettingsPanel["session"];
    (el as unknown as { mcpHealth: unknown }).mcpHealth = { status: "ok", mcp_enabled: false };
    el.requestUpdate();
    await el.updateComplete;
    expect(el.shadowRoot!.textContent).toContain("Home Assistant");
    expect(el.shadowRoot!.querySelector(".env-table")).toBeNull();
    el.remove();
  });

  it("hides mobile nav stack during search", async () => {
    const el = mountPanel();
    (el as unknown as { layoutWide: boolean }).layoutWide = false;
    (el as unknown as { searchQuery: string }).searchQuery = "battery";
    el.requestUpdate();
    await el.updateComplete;
    expect(el.shadowRoot!.querySelector(".settings-mobile-nav-stack")).toBeNull();
    el.remove();
  });

  it("renders copy buttons for MCP helpers", async () => {
    const el = mountPanel();
    (el as unknown as { layoutWide: boolean }).layoutWide = true;
    (el as unknown as { mcpHealth: unknown }).mcpHealth = {
      status: "ok",
      mcp_enabled: true,
      mcp_auth_configured: true,
      mcp_http_mounted: true,
      mcp_http_url: "http://localhost/mcp",
    };
    el.requestUpdate();
    await el.updateComplete;
    const buttons = [...el.shadowRoot!.querySelectorAll("button")].map((b) => b.textContent?.trim());
    expect(buttons.some((t) => t?.includes("Copy"))).toBe(true);
    el.remove();
  });

  it("shows sticky Restart when can_restart", async () => {
    const el = mountPanel();
    (el as unknown as { layoutWide: boolean }).layoutWide = true;
    (el as unknown as { mcpSettings: unknown }).mcpSettings = {
      enabled: false,
      has_token: false,
      editable: true,
      can_restart: true,
      can_recreate: true,
      pending: { mcp_env: true },
      is_addon: false,
    };
    (el as unknown as { mcpPendingRestart: boolean }).mcpPendingRestart = true;
    el.requestUpdate();
    await el.updateComplete;
    const sticky = el.shadowRoot!.querySelector(".settings-sticky-bar");
    expect(sticky?.textContent).toContain("Restart service");
    expect(el.shadowRoot!.querySelector(".restart-needed")).not.toBeNull();
    el.remove();
  });

  it("renders editable MCP controls when settings are editable", async () => {
    const el = mountPanel();
    (el as unknown as { layoutWide: boolean }).layoutWide = true;
    (el as unknown as { mcpSettings: unknown }).mcpSettings = {
      enabled: false,
      has_token: false,
      editable: true,
      can_restart: false,
      can_recreate: false,
      pending: { mcp_env: false },
      is_addon: false,
    };
    el.requestUpdate();
    await el.updateComplete;
    expect(el.shadowRoot!.textContent).toContain("Save MCP");
    el.remove();
  });
});

describe("SettingsPanel Safety heartbeat entity", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("uses solar-entity-input with input_datetime and shows friendly name", async () => {
    const el = mountPanel({
      entitiesConnected: true,
      entities: [
        {
          entity_id: "input_datetime.solar_optimizer_heartbeat",
          name: "Solar optimizer heartbeat",
          domain: "input_datetime",
        },
      ],
      config: {
        site: { latitude: 0, longitude: 0 },
        battery: {},
        reserve: {},
        forecast: {},
        control: {},
        engine: {},
        inverter: { read: {}, write: {} },
        ha: { base_url: "http://ha.local", has_token: false },
        fail_safe: {
          heartbeat_enabled: true,
          heartbeat_entity: "input_datetime.solar_optimizer_heartbeat",
        },
        grid_charge: {},
      } as SettingsPanel["config"],
    });
    (el as unknown as { layoutWide: boolean }).layoutWide = true;
    (el as unknown as { activeNav: string }).activeNav = "safety";
    el.requestUpdate();
    await el.updateComplete;

    const input = el.shadowRoot!.querySelector(
      "#settings-section-safety solar-entity-input",
    ) as HTMLElement & {
      domains: string[];
      entityId: string;
      updateComplete: Promise<boolean>;
      shadowRoot: ShadowRoot | null;
    };
    expect(input).not.toBeNull();
    expect(input.domains).toBe(INPUT_DATETIME_DOMAINS);
    expect(input.entityId).toBe("input_datetime.solar_optimizer_heartbeat");
    await input.updateComplete;
    expect(input.shadowRoot!.querySelector("input")!.value).toBe("Solar optimizer heartbeat");
    const opt = input.shadowRoot!.querySelector("option");
    expect(opt?.value).toBe("Solar optimizer heartbeat");
    el.remove();
  });
});
