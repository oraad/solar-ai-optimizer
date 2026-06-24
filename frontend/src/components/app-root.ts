import { LitElement, css, html } from "lit";
import { customElement, state } from "lit/decorators.js";

import { api, AuthRequiredError, live } from "../api.js";
import { sharedStyles } from "../styles.js";
import type {
  AppConfigView,
  ExecutionResult,
  ForecastBundle,
  GridStats,
  SessionInfo,
  ShedResult,
  SystemStatus,
  UpdateInfo,
} from "../types.js";

import "./status-cards.js";
import "./decision-panel.js";
import "./grid-stats-card.js";
import "./overrides-panel.js";
import "./forecast-chart.js";
import "./history-view.js";
import "./assistant-panel.js";
import "./load-shedding-panel.js";
import "./settings-panel.js";
import "./login-page.js";
import "./toast-host.js";

type Tab = "overview" | "forecast" | "history" | "assistant" | "settings" | "load_shedding";

const ALL_TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "overview", label: "Overview", icon: "\u25A0" },
  { id: "forecast", label: "Forecast", icon: "\u2600" },
  { id: "history", label: "History", icon: "\u29D6" },
  { id: "assistant", label: "Assistant", icon: "\u2709" },
  { id: "load_shedding", label: "Load shedding", icon: "\u26A1" },
  { id: "settings", label: "Settings", icon: "\u2699" },
];

const VIEWER_TABS = ALL_TABS.filter(
  (t) => t.id !== "settings" && t.id !== "assistant" && t.id !== "load_shedding",
);

const MOBILE_TAB_LABELS: Partial<Record<Tab, string>> = {
  load_shedding: "Shedding",
  assistant: "Chat",
};

type StatusAlert = { label: string; className: string; title?: string; onClick?: () => void };

const UPDATE_FORCE_INTERVAL_MS = 15 * 60 * 1000;

@customElement("solar-app")
export class SolarApp extends LitElement {
  static styles = [
    sharedStyles,
    css`
      :host {
        display: block;
        min-height: 100%;
        box-sizing: border-box;
      }
      .topbar {
        position: sticky;
        top: 0;
        z-index: 20;
        backdrop-filter: blur(10px);
        background: var(--panel);
        background: color-mix(in srgb, var(--bg) 78%, transparent);
        border-bottom: 1px solid var(--border);
        padding-top: var(--safe-top, env(safe-area-inset-top, 0px));
      }
      .topbar-inner {
        max-width: 1400px;
        margin: 0 auto;
        padding: 12px var(--app-pad, 20px);
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        flex-wrap: wrap;
      }
      .brand { display: flex; align-items: center; gap: 12px; }
      .brand .sun {
        font-size: 1.5rem;
        width: 38px;
        height: 38px;
        display: grid;
        place-items: center;
        border-radius: 11px;
        background: linear-gradient(150deg, var(--accent), var(--accent-2));
        color: #1a1205;
        box-shadow: var(--shadow);
      }
      .brand h1 { margin: 0; font-size: 1.15rem; font-weight: 700; letter-spacing: -0.01em; }
      .brand .sub { font-size: 0.72rem; color: var(--muted); }
      .status-strip { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
      .status-menu { position: relative; }
      .status-menu-btn {
        min-height: 34px;
        padding: 4px 10px;
        font-size: 0.78rem;
      }
      .status-menu-panel {
        display: none;
        position: absolute;
        top: calc(100% + 6px);
        right: 0;
        z-index: 30;
        min-width: 180px;
        padding: 8px;
        border-radius: var(--radius-sm);
        border: 1px solid var(--border);
        background: var(--panel);
        box-shadow: var(--shadow-lg);
        flex-direction: column;
        gap: 6px;
      }
      .status-menu.open .status-menu-panel { display: flex; }
      .pill.short-text .pill-long { display: none; }
      .pill.short-text .pill-short { display: inline; }
      .pill .pill-short { display: none; }
      .updated { font-size: 0.72rem; color: var(--muted); display: inline-flex; align-items: center; gap: 6px; }
      .icon-btn {
        width: 38px; height: 38px; padding: 0; display: grid; place-items: center;
        font-size: 1.05rem; border-radius: 11px;
      }

      nav {
        max-width: 1400px;
        margin: 0 auto;
        padding: 10px var(--app-pad, 20px) 0;
        display: flex;
        gap: 6px;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
      }
      nav button {
        background: transparent;
        border: 1px solid transparent;
        border-bottom: none;
        border-radius: 10px 10px 0 0;
        color: var(--muted);
        padding: 9px 16px;
        white-space: nowrap;
        display: inline-flex;
        gap: 8px;
        align-items: center;
      }
      nav button .ic { opacity: 0.8; }
      nav button:hover { color: var(--text); background: var(--panel-2); }
      nav button.active {
        color: var(--text);
        background: var(--panel);
        border-color: var(--border);
        box-shadow: 0 -2px 0 var(--accent) inset;
      }

      main {
        max-width: 1400px;
        margin: 0 auto;
        padding: var(--app-pad, 18px) var(--app-pad, 20px) calc(40px + var(--safe-bottom, env(safe-area-inset-bottom, 0px)));
      }
      .layout {
        display: grid;
        grid-template-columns: repeat(12, 1fr);
        gap: var(--gap, 16px);
        align-items: start;
        animation: fade 0.25s ease;
      }
      @keyframes fade { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
      .span-3 { grid-column: span 3; }
      .span-4 { grid-column: span 4; }
      .span-6 { grid-column: span 6; }
      .span-8 { grid-column: span 8; }
      .span-12 { grid-column: span 12; }
      .center { max-width: 860px; margin: 0 auto; width: 100%; }
      @media (max-width: 1100px) {
        .span-3, .span-4, .span-6, .span-8 { grid-column: span 12; }
      }
      @media (max-width: 760px) {
        nav {
          gap: 4px;
          padding-bottom: 4px;
          scroll-snap-type: x proximity;
        }
        nav button {
          scroll-snap-align: start;
          flex-shrink: 0;
          padding: 10px 14px;
          font-size: 0.82rem;
          min-height: 44px;
        }
        nav button .tab-label { display: inline; }
        .status-menu-btn { min-height: 44px; }
        .icon-btn { width: 44px; height: 44px; }
      }
      @media (max-width: 600px) {
        .brand .sub { display: none; }
        .updated { display: none; }
        .status-secondary { display: none; }
        .status-menu { display: block; }
      }
      @media (min-width: 601px) {
        .status-menu { display: none; }
      }
      .api-error {
        max-width: 1400px;
        margin: 0 auto;
        padding: 10px var(--app-pad, 20px) 0;
      }
      .api-error .banner {
        padding: 10px 12px;
        border-radius: var(--radius-sm);
        font-size: 0.82rem;
        border: 1px solid var(--border);
        background: color-mix(in srgb, var(--bad) 12%, var(--panel-2));
        color: var(--bad);
      }
    `,
  ];

  @state() private session: SessionInfo | null = null;
  @state() private authReady = false;
  @state() private needsLogin = false;
  @state() private status: SystemStatus | null = null;
  @state() private gridStats: GridStats | null = null;
  @state() private forecast: ForecastBundle | null = null;
  @state() private config: AppConfigView | null = null;
  @state() private execResults: ExecutionResult[] = [];
  @state() private shedResults: ShedResult[] = [];
  @state() private tab: Tab = "overview";
  @state() private theme: "dark" | "light" = "dark";
  @state() private lastUpdate = 0;
  @state() private now = Date.now();
  @state() private apiError = "";
  @state() private updateInfo: UpdateInfo | null = null;
  @state() private compactTopbar = false;
  @state() private navNarrow = false;
  @state() private statusMenuOpen = false;

  private unsub?: () => void;
  private pollTimer?: number;
  private clockTimer?: number;
  private gridStatsFetching = false;
  private lastForcedUpdateCheck = 0;
  private compactMql?: MediaQueryList;
  private navMql?: MediaQueryList;
  private onCompactChange = (): void => {
    this.compactTopbar = this.compactMql?.matches ?? false;
    if (!this.compactTopbar) this.statusMenuOpen = false;
  };
  private onNavNarrowChange = (): void => {
    this.navNarrow = this.navMql?.matches ?? false;
  };
  private onDocClick = (e: Event): void => {
    if (!this.statusMenuOpen) return;
    const path = e.composedPath();
    if (path.includes(this)) return;
    this.statusMenuOpen = false;
  };

  connectedCallback(): void {
    super.connectedCallback();
    this.compactMql = window.matchMedia("(max-width: 600px)");
    this.navMql = window.matchMedia("(max-width: 760px)");
    this.compactTopbar = this.compactMql.matches;
    this.navNarrow = this.navMql.matches;
    this.compactMql.addEventListener("change", this.onCompactChange);
    this.navMql.addEventListener("change", this.onNavNarrowChange);
    document.addEventListener("click", this.onDocClick, true);
    this.theme =
      (document.documentElement.getAttribute("data-theme") as "light" | "dark") || "dark";
    const savedTab = localStorage.getItem("solar-tab") as Tab | null;
    if (savedTab && ALL_TABS.some((t) => t.id === savedTab)) this.tab = savedTab;

    window.addEventListener("solar-plan-refresh", this.onPlanRefresh);
    window.addEventListener("solar-login-success", this.onLoginSuccess);
    window.addEventListener("solar-logout", this.onLogout);
    window.addEventListener("solar-update-info", this.onUpdateInfo as EventListener);
    void this.initAuth();
    this.clockTimer = window.setInterval(() => (this.now = Date.now()), 1000);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.compactMql?.removeEventListener("change", this.onCompactChange);
    this.navMql?.removeEventListener("change", this.onNavNarrowChange);
    document.removeEventListener("click", this.onDocClick, true);
    live.disconnect();
    this.unsub?.();
    window.removeEventListener("solar-plan-refresh", this.onPlanRefresh);
    window.removeEventListener("solar-login-success", this.onLoginSuccess);
    window.removeEventListener("solar-logout", this.onLogout);
    window.removeEventListener("solar-update-info", this.onUpdateInfo as EventListener);
    if (this.pollTimer) window.clearInterval(this.pollTimer);
    if (this.clockTimer) window.clearInterval(this.clockTimer);
  }

  private onPlanRefresh = (): void => {
    void this.refreshPlan();
  };

  private onLoginSuccess = (): void => {
    void this.initAuth();
  };

  private onLogout = (): void => {
    live.disconnect();
    this.unsub?.();
    this.unsub = undefined;
    this.session = null;
    this.authReady = true;
    this.needsLogin = true;
    this.status = null;
    this.gridStats = null;
    this.updateInfo = null;
    if (this.pollTimer) {
      window.clearInterval(this.pollTimer);
      this.pollTimer = undefined;
    }
  };

  private onUpdateInfo = (e: Event): void => {
    const detail = (e as CustomEvent<UpdateInfo>).detail;
    if (detail) this.updateInfo = detail;
  };

  private dismissBootSplash(): void {
    const el = document.getElementById("boot-splash");
    if (!el || el.classList.contains("boot-splash-out")) return;
    el.classList.add("boot-splash-out");
    const remove = () => el.remove();
    el.addEventListener("transitionend", remove, { once: true });
    window.setTimeout(remove, 300);
  }

  private async initAuth(): Promise<void> {
    this.authReady = false;
    this.needsLogin = false;
    try {
      this.session = await api.me();
      this.normalizeTabForRole();
      this.authReady = true;
      this.dismissBootSplash();
      this.startDashboard();
    } catch (e) {
      if (e instanceof AuthRequiredError) {
        this.needsLogin = true;
        this.session = null;
        this.authReady = true;
        this.dismissBootSplash();
        return;
      }
      this.authReady = true;
      this.dismissBootSplash();
      this.noteApiError(e);
    }
  }

  private startDashboard(): void {
    live.connect();
    if (!this.unsub) {
      this.unsub = live.onStatus((s) => {
        this.applyStatus(s);
      });
    }
    if (!this.pollTimer) {
      void this.bootstrap();
      this.pollTimer = window.setInterval(() => void this.refreshSlow(), 60_000);
    }
    if (this.isAdmin) {
      this.lastForcedUpdateCheck = Date.now();
      void this.refreshUpdateInfo(true);
    }
  }

  private async refreshUpdateInfo(refresh = false): Promise<void> {
    try {
      this.updateInfo = await api.updateInfo({ refresh });
    } catch {
      /* non-fatal */
    }
  }

  private applyStatus(s: SystemStatus): void {
    this.status = s;
    this.lastUpdate = Date.now();
    if (s.grid_stats) {
      this.gridStats = s.grid_stats;
    } else {
      this.gridStats = null;
      if (s.telemetry) {
        void this.refreshGridStats();
      }
    }
  }

  private get effectiveGridStats(): GridStats | null {
    return this.status?.grid_stats ?? this.gridStats ?? null;
  }

  private async refreshGridStats(): Promise<void> {
    if (this.gridStatsFetching) return;
    this.gridStatsFetching = true;
    try {
      this.gridStats = await api.gridStats();
    } catch {
      /* non-fatal; WS or next poll may recover */
    } finally {
      this.gridStatsFetching = false;
    }
  }

  private normalizeTabForRole(): void {
    const tabs = this.visibleTabs;
    if (!tabs.some((t) => t.id === this.tab)) {
      this.tab = "overview";
      localStorage.setItem("solar-tab", this.tab);
    }
  }

  private get isAdmin(): boolean {
    return this.session?.is_admin ?? false;
  }

  private get viewerTooltip(): string {
    const name = this.session?.display_name || this.session?.username;
    return name ? `Signed in as ${name} (viewer)` : "Viewer access — limited operator controls";
  }

  private get dashboardRole(): "admin" | "viewer" {
    return this.isAdmin ? "admin" : "viewer";
  }

  private get brandSubtitle(): string {
    const version = this.session?.version ? `v${this.session.version}` : "";
    const updateHint =
      this.isAdmin && this.updateInfo?.update_available && this.updateInfo.latest_version
        ? ` · v${this.updateInfo.latest_version} available`
        : "";
    const withVersion = (text: string) =>
      version ? `${text} · ${version}${updateHint}` : text;
    if (!this.isAdmin && this.session?.display_name) {
      return withVersion(this.session.display_name);
    }
    return withVersion("Resilience-first energy control");
  }

  private get visibleTabs() {
    return this.isAdmin ? ALL_TABS : VIEWER_TABS;
  }

  private noteApiError(e: unknown): void {
    const msg = e instanceof Error ? e.message : String(e);
    this.apiError = msg;
  }

  private async refreshPlan(): Promise<void> {
    try {
      const plan = await api.plan();
      this.execResults = plan.results ?? [];
      this.shedResults = plan.shed_results ?? [];
      this.apiError = "";
    } catch (e) {
      this.noteApiError(e);
    }
  }

  private async bootstrap(): Promise<void> {
    try {
      this.applyStatus(await api.status());
      this.apiError = "";
    } catch (e) {
      this.noteApiError(e);
    }
    await this.refreshSlow();
  }

  private async refreshSlow(): Promise<void> {
    try {
      this.forecast = await api.forecast();
    } catch (e) {
      this.noteApiError(e);
    }
    await this.refreshPlan();
    await this.refreshGridStats();
    if (this.isAdmin) {
      try {
        this.config = await api.config();
      } catch (e) {
        this.noteApiError(e);
      }
      const now = Date.now();
      if (now - this.lastForcedUpdateCheck >= UPDATE_FORCE_INTERVAL_MS) {
        this.lastForcedUpdateCheck = now;
        await this.refreshUpdateInfo(true);
      }
    }
  }

  private setTab(t: Tab): void {
    this.tab = t;
    localStorage.setItem("solar-tab", t);
  }

  private toggleTheme(): void {
    this.theme = this.theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", this.theme);
    try { localStorage.setItem("solar-theme", this.theme); } catch { /* ignore */ }
    window.dispatchEvent(new Event("solar-theme-change"));
  }

  private get haConnected(): boolean {
    return !!this.status?.ha_connected;
  }
  private get shadow(): boolean {
    return this.status?.shadow_mode ?? true;
  }
  private get paused(): boolean {
    return this.status?.paused ?? false;
  }

  private updatedLabel(): string {
    if (!this.lastUpdate) return "waiting for data";
    const s = Math.max(0, Math.round((this.now - this.lastUpdate) / 1000));
    if (s < 5) return "live";
    if (s < 60) return `updated ${s}s ago`;
    const m = Math.floor(s / 60);
    return `updated ${m}m ago`;
  }

  private tabDisplayLabel(t: { id: Tab; label: string }): string {
    if (this.navNarrow && MOBILE_TAB_LABELS[t.id]) return MOBILE_TAB_LABELS[t.id]!;
    return t.label;
  }

  private get secondaryAlerts(): StatusAlert[] {
    const alerts: StatusAlert[] = [];
    if (this.status?.engine_mode) {
      const suffix =
        this.status.engine_mode === "mpc" && this.status.engine_active !== "mpc" ? " (rules)" : "";
      alerts.push({
        label: `${this.status.engine_mode.toUpperCase()}${suffix}`,
        className: this.status.engine_active === "mpc" ? "good" : "warn",
      });
    }
    if (this.isAdmin && this.updateInfo?.update_available) {
      alerts.push({
        label: "UPDATE",
        className: "warn",
        title: "A newer release is available — open Settings",
        onClick: () => this.setTab("settings"),
      });
    }
    if (this.isAdmin && this.status?.forecast_misconfigured) {
      alerts.push({ label: "SET LOCATION", className: "bad" });
    }
    if (this.status?.forecast_degraded) {
      alerts.push({ label: "FORECAST DEGRADED", className: "warn" });
    }
    if (
      this.isAdmin &&
      this.status?.forecast_provider === "solcast" &&
      this.status?.solcast_configured === false
    ) {
      alerts.push({ label: "SOLCAST MISCONFIGURED", className: "bad" });
    }
    if (this.status?.telemetry_stale) {
      alerts.push({ label: "STALE DATA", className: "warn" });
    }
    return alerts;
  }

  private renderStatusPill(alert: StatusAlert): ReturnType<typeof html> {
    return html`
      <span
        class="pill ${alert.className} status-secondary"
        title=${alert.title ?? ""}
        @click=${alert.onClick}
        style=${alert.onClick ? "cursor:pointer" : ""}
      >${alert.label}</span>
    `;
  }

  private renderStatusMenu(): ReturnType<typeof html> {
    const alerts = this.secondaryAlerts;
    if (!alerts.length) return null;
    return html`
      <div class="status-menu ${this.statusMenuOpen ? "open" : ""}">
        <button
          type="button"
          class="status-menu-btn pill warn"
          aria-expanded=${this.statusMenuOpen}
          @click=${(e: Event) => {
            e.stopPropagation();
            this.statusMenuOpen = !this.statusMenuOpen;
          }}
        >
          ${alerts.length} alert${alerts.length === 1 ? "" : "s"}
        </button>
        <div class="status-menu-panel" role="menu">
          ${alerts.map(
            (a) => html`
              <span
                class="pill ${a.className}"
                role="menuitem"
                title=${a.title ?? ""}
                @click=${() => {
                  a.onClick?.();
                  this.statusMenuOpen = false;
                }}
                style=${a.onClick ? "cursor:pointer" : ""}
              >${a.label}</span>
            `,
          )}
        </div>
      </div>
    `;
  }

  private renderTabBody() {
    switch (this.tab) {
      case "forecast":
        return html`
          <div class="layout">
            <solar-forecast-chart
              class="span-8"
              .forecast=${this.forecast}
              .role=${this.dashboardRole}
            ></solar-forecast-chart>
            <solar-grid-stats
              class="span-4"
              .stats=${this.effectiveGridStats}
              .livePresent=${this.status?.telemetry?.grid_present ?? null}
            ></solar-grid-stats>
          </div>`;
      case "history":
        return html`<div class="layout"><solar-history-view class="span-12"></solar-history-view></div>`;
      case "assistant":
        return html`<div class="layout"><solar-assistant-panel class="span-12 center"></solar-assistant-panel></div>`;
      case "settings":
        return html`<div class="layout"><solar-settings-panel class="span-12 center" .config=${this.config} .status=${this.status} .session=${this.session} .updateInfo=${this.updateInfo}></solar-settings-panel></div>`;
      case "load_shedding":
        return html`<div class="layout"><solar-load-shedding-panel class="span-12 center" .config=${this.config} .status=${this.status}></solar-load-shedding-panel></div>`;
      default:
        return html`
          <div class="layout">
            <solar-status-cards
              class="span-8"
              .status=${this.status}
              .battery=${this.config?.battery ?? null}
            ></solar-status-cards>
            <solar-grid-stats
              class="span-4"
              .stats=${this.effectiveGridStats}
              .livePresent=${this.status?.telemetry?.grid_present ?? null}
            ></solar-grid-stats>
            <solar-decision-panel
              class="span-8"
              .decision=${this.status?.decision ?? null}
              .results=${this.execResults}
              .shedResults=${this.shedResults}
            ></solar-decision-panel>
            <solar-overrides-panel
              class="span-4"
              .role=${this.dashboardRole}
              .status=${this.status}
              .config=${this.config}
            ></solar-overrides-panel>
          </div>`;
    }
  }

  render() {
    if (!this.authReady) {
      return html`<solar-toast-host></solar-toast-host>`;
    }
    if (this.needsLogin) {
      return html`<solar-toast-host></solar-toast-host><solar-login-page></solar-login-page>`;
    }

    return html`
      <solar-toast-host></solar-toast-host>
      <div class="topbar">
        <div class="topbar-inner">
          <div class="brand">
            <span class="sun">&#9728;</span>
            <div>
              <h1>Solar AI Optimizer</h1>
              <div class="sub">${this.brandSubtitle}</div>
            </div>
          </div>
          <div class="status-strip">
            <span class="updated"><span class="dot ${this.haConnected ? "on" : "off"}"></span>${this.updatedLabel()}</span>
            ${!this.isAdmin
              ? html`<span class="pill warn" title=${this.viewerTooltip}>VIEWER</span>`
              : null}
            <span class="pill ${this.haConnected ? "good" : "bad"} ${this.compactTopbar ? "short-text" : ""}">
              <span class="dot ${this.haConnected ? "on" : "off"}"></span>
              <span class="pill-long">${this.haConnected ? "HA connected" : "HA offline"}</span>
              <span class="pill-short">${this.haConnected ? "HA" : "Offline"}</span>
            </span>
            <span class="pill ${this.shadow ? "warn" : "good"}">
              ${this.shadow ? "SHADOW" : "LIVE"}
            </span>
            ${this.paused
              ? html`<span class="pill bad">PAUSED</span>`
              : null}
            ${this.secondaryAlerts.map((a) => this.renderStatusPill(a))}
            ${this.renderStatusMenu()}
            <button
              class="icon-btn"
              title=${this.theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
              @click=${() => this.toggleTheme()}
            >
              ${this.theme === "dark" ? html`&#9790;` : html`&#9728;`}
            </button>
          </div>
        </div>
        <nav role="tablist">
          ${this.visibleTabs.map(
            (t) => html`
              <button
                role="tab"
                class=${this.tab === t.id ? "active" : ""}
                aria-selected=${this.tab === t.id}
                @click=${() => this.setTab(t.id)}
              >
                <span class="ic">${t.icon}</span><span class="tab-label">${this.tabDisplayLabel(t)}</span>
              </button>
            `,
          )}
        </nav>
      </div>

      ${this.apiError
        ? html`<div class="api-error"><div class="banner">${this.apiError}</div></div>`
        : null}

      <main>${this.renderTabBody()}</main>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-app": SolarApp;
  }
}
