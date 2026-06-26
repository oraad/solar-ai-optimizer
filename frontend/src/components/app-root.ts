import { LitElement, css, html } from "lit";
import { customElement, state } from "lit/decorators.js";

import { api, AuthRequiredError, live } from "../api.js";
import { setSiteTimezone } from "../date-format.js";
import { LOCALE_CHANGE_EVENT, t } from "../i18n.js";
import { LocaleController } from "../locale-controller.js";
import { sharedStyles } from "../styles.js";
import type {
  AppConfigView,
  EntityInfo,
  ExecutionResult,
  ForecastBundle,
  GridStats,
  SessionInfo,
  ShedResult,
  SystemStatus,
  UpdateInfo,
} from "../types.js";
import { updateChipLabel } from "../update-progress.js";

import "./status-cards.js";
import "./overview-hero.js";
import "./decision-panel.js";
import "./grid-stats-card.js";
import "./overrides-panel.js";
import "./forecast-chart.js";
import "./forecast-insights.js";
import "./history-view.js";
import "./assistant-panel.js";
import "./load-shedding-panel.js";
import "./settings-panel.js";
import "./login-page.js";
import "./toast-host.js";

type Tab = "overview" | "forecast" | "history" | "assistant" | "settings" | "load_shedding";

export type HistoryNavHint = {
  view?: "timeline" | "decisions" | "activity";
  activity?: "executions" | "shed" | "grid";
};

const TAB_IDS: Tab[] = [
  "overview",
  "forecast",
  "history",
  "assistant",
  "load_shedding",
  "settings",
];

const TAB_ICONS: Record<Tab, string> = {
  overview: "\u25A0",
  forecast: "\u2600",
  history: "\u29D6",
  assistant: "\u2709",
  load_shedding: "\u26A1",
  settings: "\u2699",
};

const VIEWER_TAB_IDS: Tab[] = TAB_IDS.filter(
  (id) => id !== "settings" && id !== "assistant" && id !== "load_shedding",
);

type StatusAlert = { label: string; className: string; title?: string; onClick?: () => void };

const UPDATE_FORCE_INTERVAL_MS = 15 * 60 * 1000;

@customElement("solar-app")
export class SolarApp extends LitElement {
  constructor() {
    super();
    new LocaleController(this);
  }

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
      .status-menu-panel button.menu-item {
        width: 100%;
        justify-content: flex-start;
        border: none;
        cursor: pointer;
        font: inherit;
      }
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
  @state() private entities: EntityInfo[] = [];
  @state() private entitiesConnected = false;
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
  @state() private forecastLastUpdate = 0;
  @state() private historyNavHint: HistoryNavHint | null = null;

  private unsub?: () => void;
  private pollTimer?: number;
  private clockTimer?: number;
  private gridStatsFetching = false;
  private lastForcedUpdateCheck = 0;
  private lastDecisionTs = "";
  private loadSheddingDirty = false;
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
    if (savedTab && TAB_IDS.includes(savedTab)) this.tab = savedTab;
    this.applyHash(window.location.hash);

    window.addEventListener("solar-plan-refresh", this.onPlanRefresh);
    window.addEventListener("solar-forecast-refresh", this.onForecastRefresh as EventListener);
    window.addEventListener("solar-load-shedding-dirty", this.onLoadSheddingDirty as EventListener);
    window.addEventListener("hashchange", this.onHashChange);
    window.addEventListener(LOCALE_CHANGE_EVENT, this.onLocaleChange);
    window.addEventListener("solar-login-success", this.onLoginSuccess);
    window.addEventListener("solar-logout", this.onLogout);
    window.addEventListener("solar-update-info", this.onUpdateInfo as EventListener);
    window.addEventListener("solar-reload-entities", this.onReloadEntities);
    window.addEventListener("solar-navigate-tab", this.onNavigateTab as EventListener);
    window.addEventListener("solar-history-nav-change", this.onHistoryNavChange as EventListener);
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
    window.removeEventListener("solar-forecast-refresh", this.onForecastRefresh as EventListener);
    window.removeEventListener("solar-load-shedding-dirty", this.onLoadSheddingDirty as EventListener);
    window.removeEventListener("hashchange", this.onHashChange);
    window.removeEventListener(LOCALE_CHANGE_EVENT, this.onLocaleChange);
    window.removeEventListener("solar-login-success", this.onLoginSuccess);
    window.removeEventListener("solar-logout", this.onLogout);
    window.removeEventListener("solar-update-info", this.onUpdateInfo as EventListener);
    window.removeEventListener("solar-reload-entities", this.onReloadEntities);
    window.removeEventListener("solar-navigate-tab", this.onNavigateTab as EventListener);
    window.removeEventListener("solar-history-nav-change", this.onHistoryNavChange as EventListener);
    if (this.pollTimer) window.clearInterval(this.pollTimer);
    if (this.clockTimer) window.clearInterval(this.clockTimer);
  }

  private onPlanRefresh = (): void => {
    void this.refreshPlan();
  };

  private onForecastRefresh = (e: Event): void => {
    const bundle = (e as CustomEvent<ForecastBundle | undefined>).detail;
    if (bundle) {
      this.forecast = bundle;
      this.forecastLastUpdate = Date.now();
      this.apiError = "";
    } else {
      void this.refreshForecastOnly();
    }
  };

  private onLoadSheddingDirty = (e: Event): void => {
    this.loadSheddingDirty = (e as CustomEvent<boolean>).detail === true;
  };

  private onHashChange = (): void => {
    this.applyHash(window.location.hash);
  };

  private applyHash(hash: string): void {
    const raw = hash.startsWith("#") ? hash.slice(1) : hash;
    if (!raw) return;
    const parts = raw.split("/");
    const main = parts[0] as Tab;
    const tabs = this.visibleTabIds.length ? this.visibleTabIds : TAB_IDS;
    if (!tabs.includes(main)) return;
    this.tab = main;
    localStorage.setItem("solar-tab", main);
    if (main === "history") {
      const hint: HistoryNavHint = {};
      if (parts[1] === "decisions" || parts[1] === "activity" || parts[1] === "timeline") {
        hint.view = parts[1];
      }
      if (parts[1] === "activity" && (parts[2] === "executions" || parts[2] === "shed" || parts[2] === "grid")) {
        hint.activity = parts[2];
      }
      this.historyNavHint = Object.keys(hint).length ? hint : null;
    }
  }

  private updateHash(): void {
    let hash = this.tab;
    if (this.tab === "history" && this.historyNavHint?.view) {
      hash += `/${this.historyNavHint.view}`;
      if (this.historyNavHint.view === "activity" && this.historyNavHint.activity) {
        hash += `/${this.historyNavHint.activity}`;
      }
    }
    const next = `#${hash}`;
    if (window.location.hash !== next) {
      window.history.replaceState(null, "", next);
    }
  }

  async refreshForecastOnly(): Promise<void> {
    try {
      this.forecast = await api.forecast();
      this.forecastLastUpdate = Date.now();
      this.apiError = "";
    } catch (e) {
      this.noteApiError(e);
    }
  }

  private onLocaleChange = (): void => {
    if (!this.authReady || this.needsLogin) return;
    live.disconnect();
    live.connect();
    void this.refreshSlow();
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

  private onReloadEntities = (): void => {
    void this.loadEntities();
  };

  private onNavigateTab = (e: Event): void => {
    const detail = (e as CustomEvent<Tab | { tab: Tab; history?: HistoryNavHint }>).detail;
    if (typeof detail === "string") {
      if (TAB_IDS.includes(detail)) this.setTab(detail);
      return;
    }
    if (detail?.tab && TAB_IDS.includes(detail.tab)) {
      if (detail.history) this.historyNavHint = detail.history;
      this.setTab(detail.tab);
    }
  };

  private onHistoryNavChange = (e: Event): void => {
    if (this.tab !== "history") return;
    const detail = (e as CustomEvent<HistoryNavHint>).detail;
    if (!detail?.view) return;
    this.historyNavHint = {
      view: detail.view,
      activity: detail.view === "activity" ? detail.activity : undefined,
    };
    this.updateHash();
  };

  private tabId(id: Tab): string {
    return `solar-tab-${id}`;
  }

  private tabPanelId(id: Tab): string {
    return `solar-tabpanel-${id}`;
  }

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
    setSiteTimezone(s.timezone_config ?? "auto", s.timezone_resolved ?? null);
    const decisionTs = s.decision?.ts ?? "";
    if (decisionTs && decisionTs !== this.lastDecisionTs) {
      this.lastDecisionTs = decisionTs;
      void this.refreshPlan();
    }
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
    const tabs = this.visibleTabIds;
    if (!tabs.includes(this.tab)) {
      this.tab = "overview";
      localStorage.setItem("solar-tab", this.tab);
    }
  }

  private get isAdmin(): boolean {
    return this.session?.is_admin ?? false;
  }

  private get viewerTooltip(): string {
    const name = this.session?.display_name || this.session?.username;
    return name
      ? t("ui.app.viewerTooltip", { name })
      : t("ui.app.viewerTooltipGeneric");
  }

  private get dashboardRole(): "admin" | "viewer" {
    return this.isAdmin ? "admin" : "viewer";
  }

  private get brandSubtitle(): string {
    const version = this.session?.version ? `v${this.session.version}` : "";
    const updateHint =
      this.isAdmin && this.updateInfo?.update_available && this.updateInfo.latest_version
        ? t("ui.app.versionAvailable", { version: this.updateInfo.latest_version })
        : "";
    const withVersion = (text: string) =>
      version ? `${text} · ${version}${updateHint}` : text;
    if (!this.isAdmin && this.session?.display_name) {
      return withVersion(this.session.display_name);
    }
    return withVersion(t("ui.app.brandSubtitle"));
  }

  private tabLabel(id: Tab): string {
    return t(`nav.${id}`);
  }

  private tabDisplayLabel(id: Tab): string {
    if (this.navNarrow) {
      if (id === "load_shedding") return t("nav.shedding");
      if (id === "assistant") return t("nav.chat");
    }
    return this.tabLabel(id);
  }

  private get visibleTabIds(): Tab[] {
    return this.isAdmin ? TAB_IDS : VIEWER_TAB_IDS;
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
      this.forecastLastUpdate = Date.now();
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
      await this.loadEntities();
      const now = Date.now();
      if (now - this.lastForcedUpdateCheck >= UPDATE_FORCE_INTERVAL_MS) {
        this.lastForcedUpdateCheck = now;
        await this.refreshUpdateInfo(true);
      }
    }
  }

  private async loadEntities(): Promise<void> {
    if (!this.isAdmin) return;
    try {
      const res = await api.entities();
      this.entities = res.entities;
      this.entitiesConnected = res.connected;
    } catch {
      this.entities = [];
      this.entitiesConnected = false;
    }
  }

  private setTab(nextTab: Tab): void {
    if (this.loadSheddingDirty && this.tab === "load_shedding" && nextTab !== "load_shedding") {
      if (!confirm(t("ui.loadShedding.unsavedWarning"))) return;
      this.loadSheddingDirty = false;
    }
    this.tab = nextTab;
    localStorage.setItem("solar-tab", nextTab);
    this.updateHash();
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
    if (!this.lastUpdate) return t("ui.app.waitingForData");
    const s = Math.max(0, Math.round((this.now - this.lastUpdate) / 1000));
    if (s < 5) return t("ui.app.live");
    if (s < 60) return t("ui.app.updatedSeconds", { s: String(s) });
    const m = Math.floor(s / 60);
    return t("ui.app.updatedMinutes", { m: String(m) });
  }

  private get secondaryAlerts(): StatusAlert[] {
    const alerts: StatusAlert[] = [];
    if (this.status?.engine_mode) {
      const suffix =
        this.status.engine_mode === "mpc" && this.status.engine_active !== "mpc"
          ? t("ui.app.engineMpcFallback")
          : "";
      alerts.push({
        label: `${this.status.engine_mode.toUpperCase()}${suffix}`,
        className: this.status.engine_active === "mpc" ? "good" : "warn",
      });
    }
    if (this.isAdmin && this.updateInfo?.update_in_progress) {
      const chip = updateChipLabel(this.updateInfo.update_progress);
      alerts.push({
        label: chip,
        className: "warn",
        title: t("ui.app.updateInProgressTitle"),
        onClick: () => this.setTab("settings"),
      });
    } else if (this.isAdmin && this.updateInfo?.update_available) {
      alerts.push({
        label: t("ui.app.update"),
        className: "warn",
        title: t("ui.app.updateAvailableTitle"),
        onClick: () => this.setTab("settings"),
      });
    }
    if (this.isAdmin && this.status?.forecast_misconfigured) {
      alerts.push({ label: t("ui.app.setLocation"), className: "bad" });
    }
    if (this.status?.forecast_degraded) {
      alerts.push({ label: t("ui.app.forecastDegraded"), className: "warn" });
    }
    if (
      this.isAdmin &&
      this.status?.forecast_provider === "solcast" &&
      this.status?.solcast_configured === false
    ) {
      alerts.push({ label: t("ui.app.solcastMisconfigured"), className: "bad" });
    }
    if (this.status?.telemetry_stale) {
      alerts.push({ label: t("ui.app.staleData"), className: "warn" });
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

  private renderStatusMenu(): ReturnType<typeof html> | null {
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
          ${alerts.length === 1 ? t("ui.app.alertCount", { count: String(alerts.length) }) : t("ui.app.alertCountPlural", { count: String(alerts.length) })}
        </button>
        <div class="status-menu-panel" role="menu">
          ${alerts.map(
            (a) => html`
              <button
                type="button"
                class="pill ${a.className} menu-item"
                role="menuitem"
                title=${a.title ?? ""}
                @click=${() => {
                  a.onClick?.();
                  this.statusMenuOpen = false;
                }}
              >${a.label}</button>
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
              .forecastLastUpdate=${this.forecastLastUpdate}
              .now=${this.now}
            ></solar-forecast-chart>
            <solar-forecast-insights
              class="span-4"
              .forecast=${this.forecast}
              .status=${this.status}
              .gridStats=${this.effectiveGridStats}
              .livePresent=${this.status?.telemetry?.grid_present ?? null}
            ></solar-forecast-insights>
          </div>`;
      case "history":
        return html`<div class="layout"><solar-history-view class="span-12" .entities=${this.entities} .navHint=${this.historyNavHint}></solar-history-view></div>`;
      case "assistant":
        return html`<div class="layout"><solar-assistant-panel class="span-12 center"></solar-assistant-panel></div>`;
      case "settings":
        return html`<div class="layout"><solar-settings-panel class="span-12 center" .config=${this.config} .status=${this.status} .session=${this.session} .updateInfo=${this.updateInfo} .entities=${this.entities} .entitiesConnected=${this.entitiesConnected}></solar-settings-panel></div>`;
      case "load_shedding":
        return html`<div class="layout"><solar-load-shedding-panel class="span-12 center" .config=${this.config} .entities=${this.entities} .entitiesConnected=${this.entitiesConnected} .status=${this.status} .shedResults=${this.shedResults}></solar-load-shedding-panel></div>`;
      default:
        return html`
          <div class="layout">
            <solar-overview-hero
              class="span-12"
              .status=${this.status}
            ></solar-overview-hero>
            <solar-status-cards
              class="span-8"
              compact
              .status=${this.status}
              .battery=${this.config?.battery ?? null}
              .loading=${!this.status}
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
              .role=${this.dashboardRole}
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
              <h1>${t("app.title")}</h1>
              <div class="sub">${this.brandSubtitle}</div>
            </div>
          </div>
          <div class="status-strip">
            <span class="updated"><span class="dot ${this.haConnected ? "on" : "off"}"></span>${this.updatedLabel()}</span>
            ${!this.isAdmin
              ? html`<span class="pill warn" title=${this.viewerTooltip}>${t("ui.app.viewer")}</span>`
              : null}
            <span class="pill ${this.haConnected ? "good" : "bad"} ${this.compactTopbar ? "short-text" : ""}">
              <span class="dot ${this.haConnected ? "on" : "off"}"></span>
              <span class="pill-long">${this.haConnected ? t("ui.app.haConnected") : t("ui.app.haOffline")}</span>
              <span class="pill-short">${this.haConnected ? t("ui.app.haShort") : t("ui.app.offlineShort")}</span>
            </span>
            <span class="pill ${this.shadow ? "warn" : "good"}">
              ${this.shadow ? t("ui.app.shadow") : t("ui.app.liveMode")}
            </span>
            ${this.paused
              ? html`<span class="pill bad">${t("ui.app.paused")}</span>`
              : null}
            ${this.secondaryAlerts.map((a) => this.renderStatusPill(a))}
            ${this.renderStatusMenu()}
            <button
              class="icon-btn"
              title=${this.theme === "dark" ? t("ui.app.themeDark") : t("ui.app.themeLight")}
              aria-label=${this.theme === "dark" ? t("ui.app.themeDark") : t("ui.app.themeLight")}
              @click=${() => this.toggleTheme()}
            >
              ${this.theme === "dark" ? html`&#9790;` : html`&#9728;`}
            </button>
          </div>
        </div>
        <nav role="tablist" aria-label=${t("app.title")}>
          ${this.visibleTabIds.map(
            (id) => html`
              <button
                type="button"
                role="tab"
                id=${this.tabId(id)}
                aria-controls=${this.tabPanelId(id)}
                class=${this.tab === id ? "active" : ""}
                aria-selected=${this.tab === id}
                @click=${() => this.setTab(id)}
              >
                <span class="ic">${TAB_ICONS[id]}</span><span class="tab-label">${this.tabDisplayLabel(id)}</span>
              </button>
            `,
          )}
        </nav>
      </div>

      ${this.apiError
        ? html`<div class="api-error"><div class="banner">${this.apiError}</div></div>`
        : null}

      <main>
        <div
          role="tabpanel"
          id=${this.tabPanelId(this.tab)}
          aria-labelledby=${this.tabId(this.tab)}
        >
          ${this.renderTabBody()}
        </div>
      </main>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-app": SolarApp;
  }
}
