import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { api, getApiToken, getBase, setApiToken, type HealthInfo, type McpSettingsInfo } from "../api.js";
import { entityLabel, fieldLabel, INVERTER_READ_ENTITY_KEYS, optimizationPriorityLabel, pvLabel, sectionTitle } from "../field-labels.js";
import { entityHelp, fieldHelp, priorityEffectHelp, pvHelp, sectionHelp } from "../field-help.js";
import { labelWithTip } from "../label-tip.js";
import { formatDateTime, getDateFormat, setDateFormat, type DateDisplayFormat } from "../date-format.js";
import { getLocale, setLocale, t, type AppLocale } from "../i18n.js";
import { LOCALES } from "../locales/manifest.js";
import { LocaleController } from "../locale-controller.js";
import { sharedStyles } from "../styles.js";
import { dismissToast, runWithToast, showToast, updateToast } from "../toast.js";
import "./azimuth-input.js";
import "./entity-input.js";
import "./info-tip.js";
import "./timezone-input.js";
import {
  SETTINGS_CATEGORIES,
  SETTINGS_NAV,
  categoryForNav,
  navItemsForCategory,
  type SettingsCategory,
  type SettingsNavId,
} from "../settings-nav.js";
import {
  SAVE_SECTIONS,
  buildSetupChecklist,
  checklistNeedsAttention,
  configSnapshot,
  isConfigDirty,
  matchesSettingsSearch,
  validateConfigDraft,
  type ValidationIssue,
} from "../settings-utils.js";
import {
  readSettingsMobileNavHeightPx,
  releaseAfterProgrammaticScroll,
  sectionObserverRootMargin,
} from "../scroll-offset.js";
import type { AppConfigView, EntityInfo, ReleaseSummary, SessionInfo, SystemStatus, UpdateInfo, UpdateProgress } from "../types.js";
import { renderMarkdown } from "../markdown.js";
import {
  activeStageIndex,
  flowStages,
  progressHeaderTitle,
  stageLabel,
  updateLogHint,
} from "../update-progress.js";

type Section = Record<string, unknown>;

const DEFAULT_PRIORITY_ORDER = [
  "resilience",
  "savings",
  "self_sufficiency",
] as const;

const SCHEMA_DOWNGRADE_NOTE =
  "If you saved config on a newer release, downgrading may ignore newer settings keys " +
  "(e.g. grid_charge.max_grid_charge_a on releases before schema v3).";

type OptimizationPriorityKey = (typeof DEFAULT_PRIORITY_ORDER)[number];

// Read-only helper fields returned by the API that must not be edited.
const HIDDEN_FIELDS = new Set(["has_token"]);

// Expected HA domain for each inverter capability, used to scope autocomplete.
const READ_DOMAIN: Record<string, string> = { grid_present: "binary_sensor" };
const WRITE_DOMAIN: Record<string, string> = {
  grid_charge_enable: "switch",
  max_grid_charge_current: "number",
};
const WRITE_ENTITY_KEYS = Object.keys(WRITE_DOMAIN);

const MCP_STDIO_SNIPPET = `{
  "mcpServers": {
    "solar-ai-optimizer": {
      "command": "docker",
      "args": [
        "compose",
        "--profile",
        "mcp",
        "-f",
        "docker-compose.yml",
        "run",
        "--rm",
        "--no-TTY",
        "mcp-stdio"
      ],
      "env": {
        "MCP_TOKEN": "<your-token>"
      }
    }
  }
}`;

function isScalar(v: unknown): v is number | string | boolean {
  return typeof v === "number" || typeof v === "string" || typeof v === "boolean";
}

@customElement("solar-settings-panel")
export class SettingsPanel extends LitElement {
  constructor() {
    super();
    new LocaleController(this);
  }

  static styles = [
    sharedStyles,
    css`
      :host {
        display: block;
        --settings-mobile-nav-height: 0px;
      }
      details { margin-bottom: 10px; border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; }
      summary { cursor: pointer; font-weight: 600; color: var(--muted); text-transform: capitalize; }
      .summary-label { display: inline-flex; align-items: center; gap: 4px; }
      .field label { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 2px; }
      .fields { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 14px; margin-top: 10px; }
      @media (max-width: 700px) {
        .fields { grid-template-columns: 1fr; }
        summary { font-size: 0.82rem; }
      }
      .field { display: flex; flex-direction: column; gap: 3px; }
      .field label { font-size: 0.75rem; color: var(--muted); }
      .field input, .field select { width: 100%; box-sizing: border-box; }
      textarea { width: 100%; box-sizing: border-box; min-height: 160px; font-family: ui-monospace, monospace; font-size: 0.8rem; background: var(--panel-2); color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 8px; }
      .buttons { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
      button.link { background: none; border: none; color: var(--accent, #6ad); padding: 0; cursor: pointer; text-decoration: underline; font: inherit; }
      .release-notes {
        margin-top: 10px;
        max-height: 240px;
        overflow: auto;
        padding: 10px 12px;
        border-radius: 8px;
        border: 1px solid var(--border);
        background: var(--panel-2);
        font-size: 0.8rem;
        line-height: 1.45;
        word-break: break-word;
      }
      .release-notes :is(h1, h2, h3, h4) { margin: 0.6em 0 0.35em; font-size: 0.95rem; }
      .release-notes :is(ul, ol) { margin: 0.35em 0; padding-inline-start: 1.25em; }
      .release-notes p { margin: 0.35em 0; }
      .release-notes a { color: var(--accent, #6ad); }
      .release-notes code {
        font-family: ui-monospace, monospace;
        font-size: 0.85em;
        background: var(--panel);
        padding: 1px 4px;
        border-radius: 4px;
      }
      .release-notes pre {
        overflow: auto;
        padding: 8px;
        border-radius: 6px;
        background: var(--panel);
        font-size: 0.75rem;
      }
      .release-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.8rem; }
      .release-table th, .release-table td {
        text-align: start;
        padding: 6px 8px;
        border-bottom: 1px solid var(--border);
        vertical-align: top;
      }
      .release-table th { color: var(--muted); font-weight: 600; }
      .release-badge {
        display: inline-block;
        margin-inline-start: 6px;
        padding: 1px 6px;
        border-radius: 999px;
        font-size: 0.65rem;
        font-weight: 600;
        background: color-mix(in srgb, var(--muted) 18%, transparent);
        color: var(--muted);
      }
      .release-badge.current { color: var(--good, #6c6); background: color-mix(in srgb, var(--good, #6c6) 18%, transparent); }
      .release-badge.newer { color: var(--accent); background: color-mix(in srgb, var(--accent) 18%, transparent); }
      .release-badge.prerelease { color: var(--warn, #c90); background: color-mix(in srgb, var(--warn, #c90) 18%, transparent); }
      .settings-footer {
        margin-top: 16px;
        padding-top: 12px;
        border-top: 1px solid var(--border);
      }
      .recovery-banner {
        margin-top: 12px;
        padding: 10px 12px;
        border-radius: 8px;
        border: 1px solid color-mix(in srgb, var(--warn, #c90) 45%, var(--border));
        background: color-mix(in srgb, var(--warn, #c90) 12%, var(--panel-2));
      }
      .recovery-banner p { margin: 0 0 8px; font-size: 0.8rem; line-height: 1.45; }
      .upgrade-cmd {
        margin-top: 10px;
        padding: 10px 12px;
        border-radius: 8px;
        border: 1px solid var(--border);
        background: var(--panel-2);
        font-family: ui-monospace, monospace;
        font-size: 0.75rem;
        white-space: pre-wrap;
        word-break: break-word;
      }
      .badge-update {
        display: inline-block;
        margin-inline-start: 8px;
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 0.68rem;
        font-weight: 600;
        background: color-mix(in srgb, var(--accent) 22%, transparent);
        color: var(--accent);
        vertical-align: middle;
      }
      .update-progress {
        margin-top: 12px;
        padding: 10px 12px;
        border-radius: 8px;
        border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--border));
        background: color-mix(in srgb, var(--accent) 8%, var(--panel-2));
      }
      .update-progress h4 {
        margin: 0 0 8px;
        font-size: 0.82rem;
        font-weight: 600;
      }
      .update-step {
        display: flex;
        align-items: flex-start;
        gap: 8px;
        font-size: 0.78rem;
        line-height: 1.4;
        padding: 3px 0;
        color: var(--muted);
      }
      .update-step.done { color: var(--text); }
      .update-step.active { color: var(--text); font-weight: 600; }
      .update-step-icon {
        width: 14px;
        flex-shrink: 0;
        text-align: center;
        margin-top: 1px;
      }
      .update-step-detail {
        display: block;
        font-size: 0.72rem;
        font-weight: 400;
        color: var(--muted);
        margin-top: 2px;
      }
      .update-pull-track {
        width: 100%;
        height: 4px;
        border-radius: 999px;
        background: color-mix(in srgb, var(--border) 80%, transparent);
        margin: 4px 0 2px 22px;
        max-width: calc(100% - 22px);
        overflow: hidden;
      }
      .update-pull-bar {
        height: 100%;
        border-radius: 999px;
        background: var(--accent);
        transition: width 0.3s ease;
      }
      .update-spinner {
        display: inline-block;
        width: 12px;
        height: 12px;
        border: 2px solid color-mix(in srgb, var(--accent) 25%, transparent);
        border-top-color: var(--accent);
        border-radius: 50%;
        animation: update-spin 0.8s linear infinite;
      }
      @keyframes update-spin {
        to { transform: rotate(360deg); }
      }
      @media (prefers-reduced-motion: reduce) {
        .update-spinner { animation: none; border-top-color: var(--accent); }
      }
      .settings-shell {
        display: grid;
        grid-template-columns: 200px minmax(0, 1fr);
        gap: 16px;
        align-items: start;
      }
      @media (max-width: 899px) {
        .settings-shell { grid-template-columns: 1fr; }
      }
      .settings-header {
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 12px;
      }
      .settings-search {
        flex: 1;
        min-width: 140px;
        max-width: 280px;
      }
      .settings-search input {
        width: 100%;
        box-sizing: border-box;
        padding: 6px 10px;
        border-radius: 8px;
        border: 1px solid var(--border);
        background: var(--panel-2);
        color: var(--text);
        font-size: 0.82rem;
      }
      .settings-nav {
        display: flex;
        flex-direction: column;
        gap: 2px;
        position: sticky;
        top: calc(var(--app-chrome-height, 72px) + 8px);
        z-index: 1;
      }
      .settings-mobile-section-nav {
        display: none;
      }
      @media (max-width: 899px) {
        .settings-nav {
          flex-direction: row;
          flex-wrap: nowrap;
          overflow-x: auto;
          position: static;
          padding-bottom: 4px;
          -webkit-overflow-scrolling: touch;
        }
        .settings-mobile-section-nav {
          display: flex;
          flex-direction: row;
          flex-wrap: nowrap;
          overflow-x: auto;
          gap: 6px;
          margin-bottom: 10px;
          -webkit-overflow-scrolling: touch;
        }
      }
      .nav-category-label {
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--muted);
        margin: 10px 0 4px;
        padding-inline-start: 8px;
      }
      @media (max-width: 899px) {
        .nav-category-label { display: none; }
      }
      .nav-item {
        display: block;
        width: 100%;
        text-align: start;
        padding: 7px 10px;
        border: none;
        border-radius: 8px;
        background: transparent;
        color: var(--muted);
        font: inherit;
        font-size: 0.8rem;
        cursor: pointer;
        white-space: nowrap;
      }
      @media (max-width: 899px) {
        .nav-item {
          width: auto;
          flex-shrink: 0;
          border: 1px solid var(--border);
          background: var(--panel-2);
        }
      }
      .nav-item:hover { color: var(--text); background: var(--panel-2); }
      .nav-item.active {
        color: var(--text);
        font-weight: 600;
        background: color-mix(in srgb, var(--accent) 14%, var(--panel-2));
        border-color: color-mix(in srgb, var(--accent) 35%, var(--border));
      }
      .nav-pill {
        padding: 6px 12px;
        border-radius: 999px;
        border: 1px solid var(--border);
        background: var(--panel-2);
        color: var(--muted);
        font: inherit;
        font-size: 0.78rem;
        cursor: pointer;
        white-space: nowrap;
        flex-shrink: 0;
      }
      .nav-pill.active {
        color: var(--text);
        font-weight: 600;
        border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
        background: color-mix(in srgb, var(--accent) 12%, var(--panel-2));
      }
      .category-pills {
        display: none;
        gap: 6px;
        flex-wrap: wrap;
        margin-bottom: 10px;
      }
      @media (max-width: 899px) {
        .category-pills { display: flex; }
        .settings-nav-desktop { display: none; }
      }
      @media (min-width: 900px) {
        .category-pills { display: none; }
      }
      .settings-content { min-width: 0; }
      .settings-nav-target {
        scroll-margin-top: calc(var(--app-chrome-height, 72px) + 8px + var(--settings-mobile-nav-height, 0px));
      }
      .mcp-status-pill {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        border: 1px solid var(--border);
        background: var(--panel-2);
        color: var(--muted);
      }
      .mcp-status-pill.active {
        color: var(--good, #3a8);
        border-color: color-mix(in srgb, var(--good, #3a8) 40%, var(--border));
        background: color-mix(in srgb, var(--good, #3a8) 12%, var(--panel-2));
      }
      .mcp-status-pill.warn {
        color: var(--warn, #c90);
        border-color: color-mix(in srgb, var(--warn, #c90) 40%, var(--border));
        background: color-mix(in srgb, var(--warn, #c90) 12%, var(--panel-2));
      }
      .mcp-snippet {
        margin: 8px 0 0;
        padding: 10px 12px;
        border-radius: 8px;
        border: 1px solid var(--border);
        background: var(--panel-2);
        font-size: 0.72rem;
        overflow: auto;
        white-space: pre-wrap;
        word-break: break-word;
      }
      .env-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.78rem;
        margin-top: 8px;
      }
      .env-table th,
      .env-table td {
        text-align: start;
        padding: 6px 8px;
        border-bottom: 1px solid var(--border);
        vertical-align: top;
      }
      .env-table code {
        font-size: 0.76rem;
      }
      .section-panel {
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 12px 14px;
        margin-bottom: 10px;
      }
      .section-panel h4 {
        margin: 0 0 10px;
        font-size: 0.88rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
      }
      .persistence-badge {
        display: inline-block;
        padding: 1px 7px;
        border-radius: 999px;
        font-size: 0.62rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        background: color-mix(in srgb, var(--muted) 16%, transparent);
        color: var(--muted);
      }
      .persistence-badge.browser {
        color: var(--accent);
        background: color-mix(in srgb, var(--accent) 14%, transparent);
      }
      .persistence-badge.immediate {
        color: var(--warn, #c90);
        background: color-mix(in srgb, var(--warn, #c90) 14%, transparent);
      }
      .checklist-banner {
        margin-bottom: 14px;
        padding: 12px 14px;
        border-radius: 8px;
        border: 1px solid color-mix(in srgb, var(--accent) 30%, var(--border));
        background: color-mix(in srgb, var(--accent) 6%, var(--panel-2));
      }
      .checklist-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        margin-bottom: 8px;
      }
      .checklist-header h4 { margin: 0; font-size: 0.85rem; }
      .checklist-progress {
        height: 4px;
        border-radius: 999px;
        background: var(--border);
        margin-bottom: 10px;
        overflow: hidden;
      }
      .checklist-progress-bar {
        height: 100%;
        background: var(--accent);
        transition: width 0.2s ease;
      }
      .checklist-row {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 0.8rem;
        padding: 3px 0;
      }
      .checklist-row.done { color: var(--muted); }
      .checklist-icon { width: 16px; flex-shrink: 0; text-align: center; }
      .link-card {
        margin-top: 12px;
        padding: 10px 12px;
        border-radius: 8px;
        border: 1px solid var(--border);
        background: var(--panel-2);
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;
        justify-content: space-between;
      }
      .pv-array-card {
        position: relative;
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 10px 44px 10px 12px;
        margin-bottom: 10px;
      }
      .pv-array-dismiss {
        position: absolute;
        top: 8px;
        right: 8px;
        width: 32px;
        height: 32px;
        padding: 0;
        display: grid;
        place-items: center;
        font-size: 1.1rem;
        line-height: 1;
      }
      .pv-array-title {
        font-size: 0.85rem;
        font-weight: 600;
        margin-bottom: 8px;
        color: var(--text);
      }
      .mode-toggle {
        display: inline-flex;
        border: 1px solid var(--border);
        border-radius: 8px;
        overflow: hidden;
      }
      .mode-toggle button {
        border: none;
        border-radius: 0;
        background: var(--panel-2);
        color: var(--muted);
        padding: 6px 14px;
        font-size: 0.8rem;
        cursor: pointer;
      }
      .mode-toggle button.active {
        background: color-mix(in srgb, var(--accent) 18%, var(--panel-2));
        color: var(--text);
        font-weight: 600;
      }
      .priority-row {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 6px;
        padding: 6px 8px;
        border-radius: 8px;
        border: 1px solid var(--border);
        background: var(--panel-2);
        cursor: grab;
      }
      .priority-row.dragging { opacity: 0.5; }
      .priority-handle { color: var(--muted); font-size: 0.9rem; user-select: none; }
      .validation-banner {
        margin-bottom: 10px;
        padding: 8px 12px;
        border-radius: 8px;
        border: 1px solid color-mix(in srgb, var(--bad, #c66) 40%, var(--border));
        background: color-mix(in srgb, var(--bad, #c66) 10%, var(--panel-2));
        font-size: 0.8rem;
      }
      .validation-banner ul { margin: 4px 0 0; padding-inline-start: 1.2em; }
      .settings-sticky-bar {
        position: sticky;
        bottom: 0;
        z-index: 2;
        margin: 16px calc(-1 * var(--card-pad, 18px)) calc(-1 * var(--card-pad, 18px));
        padding: 10px 18px calc(10px + env(safe-area-inset-bottom, 0px));
        border-top: 1px solid var(--border);
        background: color-mix(in srgb, var(--panel) 92%, transparent);
        backdrop-filter: blur(8px);
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        align-items: center;
        justify-content: space-between;
      }
      .dirty-indicator {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 0.8rem;
        color: var(--warn, #c90);
      }
      .dirty-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--warn, #c90);
      }
      .sticky-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
      .sticky-actions button.restart-needed {
        border-color: var(--warn, #c97800);
        color: var(--warn, #c97800);
      }
      .mcp-pending-banner {
        margin: 8px 0;
        padding: 10px 12px;
        border-radius: var(--radius, 8px);
        border: 1px solid color-mix(in srgb, var(--warn, #c97800) 45%, transparent);
        background: color-mix(in srgb, var(--warn, #c97800) 12%, transparent);
      }
    `,
  ];

  @property({ attribute: false }) config: AppConfigView | null = null;
  @property({ attribute: false }) status: SystemStatus | null = null;
  @property({ attribute: false }) session: SessionInfo | null = null;
  @property({ attribute: false }) updateInfo: UpdateInfo | null = null;
  @property({ attribute: false }) entities: EntityInfo[] = [];
  @property({ attribute: false }) entitiesConnected = false;

  @state() private draft: AppConfigView | null = null;
  @state() private raw = "";
  @state() private busy = false;
  @state() private apiToken = "";
  @state() private pairCode: string | null = null;
  @state() private pairExpiresIn = 0;
  @state() private pairClients: Array<{
    id: string;
    name: string;
    created_at?: string;
    last_used_at?: string | null;
  }> = [];
  @state() private pairBusy = false;
  @state() private haOauthConnected = false;
  @state() private haOauthDegraded = false;
  @state() private haOauthBusy = false;
  @state() private haAuthMode: string | null = null;
  @state() private haWsErrorClass: string | null = null;
  @state() private haWsLastError: string | null = null;
  @state() private haWsCircuitOpen = false;
  @state() private haConnected = false;
  @state() private haRetryBusy = false;
  @state() private mpcAvailable = false;
  @state() private mlAvailable = false;
  @state() private mlLoadEnabled = false;
  @state() private updateBusy = false;
  @state() private updateChecking = false;
  @state() private expandedRelease: string | null = null;
  @state() private installRecoveryOffer = false;
  @state() private updateProgress: UpdateProgress | null = null;
  @state() private updateHealthWait = false;
  @state() private updateWatchActive = false;
  @state() private dateFormat: DateDisplayFormat = "locale";
  @state() private locale: AppLocale = "en";
  @state() private activeNav: SettingsNavId = "setup_ha";
  @state() private mobileCategory: SettingsCategory = "setup";
  @state() private searchQuery = "";
  @state() private checklistDismissed = false;
  @state() private validationIssues: ValidationIssue[] = [];
  @state() private dragPriorityIndex: number | null = null;
  @state() private mcpHealth: HealthInfo | null = null;
  @state() private mcpSettings: McpSettingsInfo | null = null;
  @state() private mcpDraftEnabled = false;
  @state() private mcpDraftToken = "";
  @state() private mcpTokenDirty = false;
  @state() private mcpGeneratedToken: string | null = null;
  @state() private mcpBusy = false;
  @state() private restartBusy = false;
  @state() private mcpPendingRestart = false;

  private savedSnapshot = "";
  private layoutWide = false;
  private layoutMedia: MediaQueryList | null = null;
  private pendingScrollNav: SettingsNavId | null = null;
  private suppressScrollSpy = false;
  private sectionObserver: IntersectionObserver | null = null;
  private mobileNavObserver: ResizeObserver | null = null;
  private mcpRefreshTimer: number | null = null;
  private sectionObserverRootMargin = "";
  private updateWatchToken = 0;
  private onBeforeUnload = (e: BeforeUnloadEvent) => {
    if (this.isDirty) {
      e.preventDefault();
    }
  };
  private onDateFormatChange = () => {
    this.dateFormat = getDateFormat();
    this.requestUpdate();
  };
  private onLocaleChange = () => {
    this.locale = getLocale();
    this.requestUpdate();
  };
  private onLayoutMediaChange = () => {
    this.layoutWide = this.layoutMedia?.matches ?? false;
    this.requestUpdate();
  };

  connectedCallback(): void {
    super.connectedCallback();
    this.dateFormat = getDateFormat();
    this.locale = getLocale();
    window.addEventListener("solar-date-format-change", this.onDateFormatChange);
    window.addEventListener("solar-locale-change", this.onLocaleChange);
    window.addEventListener("beforeunload", this.onBeforeUnload);
    this.layoutMedia = window.matchMedia("(min-width: 900px)");
    this.layoutWide = this.layoutMedia.matches;
    this.layoutMedia.addEventListener("change", this.onLayoutMediaChange);
    this.apiToken = getApiToken();
    if (this.config) this.setDraft(this.config);
    void this.loadConfig();
    void this.loadCapabilities();
    void this.refreshPairStatus();
    void this.refreshHaOauthStatus();
    void this.refreshMcpStatus();
    this.mcpRefreshTimer = window.setInterval(() => void this.refreshMcpStatus(), 30_000);
    this.maybeResumeUpdateWatch();
  }

  protected firstUpdated(): void {
    this.syncMobileNavHeight();
    const stack = this.renderRoot.querySelector(".settings-mobile-nav-stack");
    if (stack instanceof HTMLElement) {
      this.mobileNavObserver = new ResizeObserver(() => this.syncMobileNavHeight());
      this.mobileNavObserver.observe(stack);
    }
  }

  disconnectedCallback(): void {
    window.removeEventListener("solar-date-format-change", this.onDateFormatChange);
    window.removeEventListener("solar-locale-change", this.onLocaleChange);
    window.removeEventListener("beforeunload", this.onBeforeUnload);
    this.layoutMedia?.removeEventListener("change", this.onLayoutMediaChange);
    this.layoutMedia = null;
    this.sectionObserver?.disconnect();
    this.sectionObserver = null;
    this.mobileNavObserver?.disconnect();
    this.mobileNavObserver = null;
    if (this.mcpRefreshTimer != null) {
      window.clearInterval(this.mcpRefreshTimer);
      this.mcpRefreshTimer = null;
    }
    super.disconnectedCallback();
  }

  private syncMobileNavHeight(): void {
    const stack = this.renderRoot.querySelector(".settings-mobile-nav-stack");
    if (!(stack instanceof HTMLElement) || this.layoutWide || this.searchQuery.trim()) {
      this.style.setProperty("--settings-mobile-nav-height", "0px");
      return;
    }
    const h = Math.ceil(stack.getBoundingClientRect().height);
    this.style.setProperty("--settings-mobile-nav-height", `${h}px`);
    this.syncSectionObserver();
  }

  private async refreshMcpStatus(): Promise<void> {
    try {
      this.mcpHealth = await api.health();
    } catch {
      /* optional until backend deployed */
    }
    try {
      this.mcpSettings = await api.mcpSettings();
      this.mcpDraftEnabled = this.mcpSettings.enabled;
      this.mcpPendingRestart = Boolean(this.mcpSettings.pending?.mcp_env);
      if (!this.mcpTokenDirty) {
        this.mcpDraftToken = "";
      }
    } catch {
      this.mcpSettings = null;
    }
  }

  private async saveMcpSettings(opts?: { generate?: boolean; clearToken?: boolean }): Promise<void> {
    if (!this.mcpSettings?.editable || this.mcpBusy) return;
    this.mcpBusy = true;
    try {
      const body: {
        enabled: boolean;
        token?: string;
        clear_token?: boolean;
        generate_token?: boolean;
      } = { enabled: this.mcpDraftEnabled };
      if (opts?.generate) body.generate_token = true;
      else if (opts?.clearToken) body.clear_token = true;
      else if (this.mcpTokenDirty && this.mcpDraftToken.trim()) {
        body.token = this.mcpDraftToken.trim();
      }
      const res = await api.putMcpSettings(body);
      this.mcpSettings = res;
      this.mcpPendingRestart = true;
      this.mcpTokenDirty = false;
      this.mcpDraftToken = "";
      if (res.token) {
        this.mcpGeneratedToken = res.token;
        showToast({ message: t("ui.settings.mcp.tokenGeneratedOnce"), variant: "success" });
      } else {
        showToast({ message: t("ui.settings.mcp.saveSuccess"), variant: "success" });
      }
      await this.refreshMcpStatus();
    } catch (e) {
      showToast({
        message: e instanceof Error ? e.message : t("ui.settings.mcp.saveFailed"),
        variant: "error",
      });
    } finally {
      this.mcpBusy = false;
    }
  }

  private async restartService(): Promise<void> {
    if (this.restartBusy || this.updateBusy || this.updateWatchActive) return;
    if (!this.mcpSettings?.can_restart && !this.updateInfo?.can_apply) return;
    if (!window.confirm(t("ui.settings.restartConfirm"))) return;
    this.restartBusy = true;
    const toastId = showToast({
      message: t("ui.settings.restarting"),
      variant: "loading",
      persistent: true,
    });
    try {
      await api.restartService();
      const deadline = Date.now() + 120_000;
      const healthStart = Date.now();
      while (Date.now() < deadline) {
        const elapsed = Math.floor((Date.now() - healthStart) / 1000);
        updateToast(toastId, {
          message: t("ui.settings.waitingRestartElapsed", { seconds: String(elapsed) }),
        });
        await new Promise((r) => setTimeout(r, 3000));
        try {
          const h = await api.health();
          if (h.status === "ok") {
            updateToast(toastId, {
              message: t("ui.settings.restartComplete"),
              variant: "success",
            });
            this.mcpPendingRestart = false;
            await this.refreshMcpStatus();
            window.setTimeout(() => dismissToast(toastId), 2500);
            return;
          }
        } catch {
          /* restarting */
        }
      }
      updateToast(toastId, {
        message: t("ui.settings.restartTimeout"),
        variant: "error",
      });
    } catch (e) {
      updateToast(toastId, {
        message: e instanceof Error ? e.message : t("ui.settings.restartFailed"),
        variant: "error",
      });
    } finally {
      this.restartBusy = false;
    }
  }

  private async recreateService(): Promise<void> {
    if (this.restartBusy || this.updateBusy || this.updateWatchActive) return;
    if (!this.mcpSettings?.can_recreate && !this.updateInfo?.can_apply) return;
    if (!window.confirm(t("ui.settings.recreateConfirm"))) return;
    this.restartBusy = true;
    const toastId = showToast({
      message: t("ui.settings.recreating"),
      variant: "loading",
      persistent: true,
    });
    try {
      await api.recreateService();
      const deadline = Date.now() + 180_000;
      const healthStart = Date.now();
      while (Date.now() < deadline) {
        const elapsed = Math.floor((Date.now() - healthStart) / 1000);
        updateToast(toastId, {
          message: t("ui.settings.waitingRestartElapsed", { seconds: String(elapsed) }),
        });
        await new Promise((r) => setTimeout(r, 3000));
        try {
          const h = await api.health();
          if (h.status === "ok") {
            updateToast(toastId, {
              message: t("ui.settings.recreateComplete"),
              variant: "success",
            });
            await this.refreshMcpStatus();
            window.setTimeout(() => {
              dismissToast(toastId);
              window.location.reload();
            }, 1500);
            return;
          }
        } catch {
          /* recreating */
        }
      }
      updateToast(toastId, {
        message: t("ui.settings.restartTimeout"),
        variant: "error",
      });
    } catch (e) {
      updateToast(toastId, {
        message: e instanceof Error ? e.message : t("ui.settings.recreateFailed"),
        variant: "error",
      });
    } finally {
      this.restartBusy = false;
    }
  }

  private async copyText(text: string, successKey: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      showToast({ message: t(successKey), variant: "success" });
    } catch {
      showToast({ message: t("ui.settings.mcp.copyFailed"), variant: "error" });
    }
  }

  protected updated(changed: Map<PropertyKey, unknown>): void {
    if (changed.has("updateInfo")) {
      this.maybeResumeUpdateWatch();
    }
    if (this.pendingScrollNav) {
      const id = this.pendingScrollNav;
      this.pendingScrollNav = null;
      this.suppressScrollSpy = true;
      requestAnimationFrame(() => {
        const el = this.renderRoot.querySelector(`#settings-section-${id}`);
        if (el instanceof HTMLElement) {
          const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
          el.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
          el.focus({ preventScroll: true });
          releaseAfterProgrammaticScroll(() => {
            this.suppressScrollSpy = false;
          }, reduceMotion);
        } else {
          this.suppressScrollSpy = false;
        }
      });
    }
    if (changed.has("searchQuery") || changed.has("layoutWide") || changed.has("mobileCategory")) {
      queueMicrotask(() => this.syncMobileNavHeight());
    }
    if (changed.has("draft") && this.draft) {
      queueMicrotask(() => {
        this.syncMobileNavHeight();
        const stack = this.renderRoot.querySelector(".settings-mobile-nav-stack");
        if (stack instanceof HTMLElement && !this.mobileNavObserver) {
          this.mobileNavObserver = new ResizeObserver(() => this.syncMobileNavHeight());
          this.mobileNavObserver.observe(stack);
        }
      });
    }
    this.syncSectionObserver();
  }

  private maybeResumeUpdateWatch(): void {
    if (this.session?.is_addon) return;
    if (this.updateWatchActive || this.updateBusy) return;
    if (!this.updateInfo?.update_in_progress) return;
    void this.resumeUpdateWatch();
  }

  private async resumeUpdateWatch(): Promise<void> {
    if (this.session?.is_addon) return;
    this.updateWatchActive = true;
    this.updateBusy = true;
    const toastId = "update-resume";
    showToast({
      id: toastId,
      message: t("ui.settings.updateInProgress"),
      variant: "loading",
      persistent: true,
    });
    try {
      const result = await this.watchUpdateCompletion({ toastId });
      if (result.ok) {
        updateToast(toastId, { message: t("ui.settings.updateCompleteReload"), variant: "success" });
        window.location.reload();
        return;
      }
      dismissToast(toastId);
      if (result.failed) {
        showToast({
          message: result.failed.message,
          variant: "error",
          persistent: true,
        });
      } else {
        this.installRecoveryOffer = true;
        showToast({
          message:
            t("ui.settings.updateTimeout"),
          variant: "error",
          persistent: true,
        });
      }
      void this.refreshUpdateInfo();
    } finally {
      this.updateWatchActive = false;
      this.updateBusy = false;
      this.updateHealthWait = false;
    }
  }

  private async loadCapabilities(): Promise<void> {
    try {
      const s = await api.status();
      this.mpcAvailable = s.mpc_available ?? false;
      this.mlAvailable = s.ml_available ?? false;
      this.mlLoadEnabled = s.ml_load_enabled ?? false;
    } catch {
      this.mpcAvailable = false;
      this.mlAvailable = false;
    }
  }

  private requestEntityReload(): void {
    window.dispatchEvent(new Event("solar-reload-entities"));
  }

  private setDraft(cfg: AppConfigView): void {
    this.draft = structuredClone(cfg);
    this.raw = JSON.stringify(cfg, null, 2);
    this.savedSnapshot = configSnapshot(cfg);
    this.validationIssues = validateConfigDraft(this.draft);
  }

  private async loadConfig(): Promise<void> {
    try {
      this.setDraft(await api.config());
    } catch { /* keep whatever we have */ }
  }

  /** Mutate a structured clone of the draft so Lit sees a new reference. */
  private patchDraft(mutator: (d: Record<string, any>) => void): void {
    if (!this.draft) return;
    const copy = structuredClone(this.draft) as Record<string, any>;
    mutator(copy);
    this.draft = copy as AppConfigView;
    this.validationIssues = validateConfigDraft(this.draft);
  }

  private get isDirty(): boolean {
    return isConfigDirty(this.draft, this.savedSnapshot);
  }

  private navLabel(labelKey: string): string {
    return t(labelKey);
  }

  private persistenceBadge(kind: "server" | "browser" | "immediate") {
    return html`<span class="persistence-badge ${kind}">${t(`ui.settings.badge.${kind}`)}</span>`;
  }

  private selectNav(id: SettingsNavId): void {
    this.activeNav = id;
    this.mobileCategory = categoryForNav(id);
    this.pendingScrollNav = id;
  }

  private selectCategory(cat: SettingsCategory): void {
    this.mobileCategory = cat;
    const first = navItemsForCategory(cat)[0];
    if (first) {
      this.activeNav = first.id;
      this.pendingScrollNav = first.id;
    }
  }

  private syncSectionObserver(): void {
    const mobileNavHeight = this.layoutWide ? 0 : readSettingsMobileNavHeightPx();
    const rootMargin = sectionObserverRootMargin(mobileNavHeight);
    if (!this.sectionObserver) {
      this.sectionObserver = new IntersectionObserver(
        (entries) => {
          if (this.suppressScrollSpy) return;
          let best: IntersectionObserverEntry | null = null;
          for (const entry of entries) {
            if (
              entry.isIntersecting &&
              (!best || entry.intersectionRatio > best.intersectionRatio)
            ) {
              best = entry;
            }
          }
          if (!best) return;
          const id = best.target.id.replace(/^settings-section-/, "") as SettingsNavId;
          if (SETTINGS_NAV.some((n) => n.id === id) && this.activeNav !== id) {
            this.activeNav = id;
            this.mobileCategory = categoryForNav(id);
          }
        },
        { rootMargin, threshold: [0, 0.1, 0.25, 0.5, 0.75, 1] },
      );
    } else if (this.sectionObserverRootMargin !== rootMargin) {
      this.sectionObserver.disconnect();
      this.sectionObserver = null;
      this.sectionObserverRootMargin = rootMargin;
      this.syncSectionObserver();
      return;
    }
    this.sectionObserverRootMargin = rootMargin;
    this.sectionObserver.disconnect();
    this.renderRoot.querySelectorAll(".settings-nav-target").forEach((el) => {
      this.sectionObserver!.observe(el);
    });
  }

  private openApiSecuritySection(): void {
    this.selectNav("system");
  }

  private openLoadSheddingTab(): void {
    window.dispatchEvent(
      new CustomEvent("solar-navigate-tab", { detail: "load_shedding", bubbles: true, composed: true }),
    );
  }

  private toastRun(
    fn: () => Promise<void>,
    loadingKey: string,
    successKey: string,
    errorFallback?: string,
  ): Promise<void> {
    return this.run(fn, t(loadingKey), t(successKey), errorFallback);
  }

  private setField(section: string, key: string, value: unknown): void {
    this.patchDraft((d) => {
      d[section] = { ...(d[section] ?? {}), [key]: value };
    });
  }

  private setNested(section: string, group: string, key: string, value: unknown): void {
    this.patchDraft((d) => {
      d[section] = d[section] ?? {};
      d[section][group] = { ...(d[section][group] ?? {}), [key]: value };
    });
  }

  private async save(): Promise<void> {
    if (!this.draft) return;
    this.validationIssues = validateConfigDraft(this.draft);
    if (this.validationIssues.length) {
      showToast({ message: t("ui.settings.validation.fixBeforeSave"), variant: "error" });
      return;
    }
    this.patchDraft((d) => {
      this.normalizeGridChargeForSave(d);
      this.normalizePriorityOrderForSave(d);
    });
    await this.toastRun(
      async () => {
        const patch: Record<string, unknown> = {};
        const draftRec = this.draft as unknown as Record<string, unknown>;
        for (const sec of SAVE_SECTIONS) {
          if (draftRec[sec] !== undefined) {
            patch[sec] = draftRec[sec];
          }
        }
        const res = await api.putConfig(patch);
        if (!res.ok) throw new Error(res.error || t("ui.shed.validationFailed"));
      },
      "ui.settings.toastSaveLoading",
      "ui.settings.toastSaveSuccess",
    );
  }

  private async applyRaw(): Promise<void> {
    await this.toastRun(
      async () => {
        const parsed = JSON.parse(this.raw);
        const res = await api.putConfig(parsed);
        if (!res.ok) throw new Error(res.error || t("ui.shed.validationFailed"));
      },
      "ui.settings.toastApplyLoading",
      "ui.settings.toastApplySuccess",
    );
  }

  private async reset(): Promise<void> {
    if (!confirm(t("ui.settings.revertConfirm"))) return;
    await this.toastRun(
      async () => {
        await api.resetConfig();
      },
      "ui.settings.toastRevertLoading",
      "ui.settings.toastRevertSuccess",
    );
  }

  private async exportConfig(): Promise<void> {
    await this.toastRun(
      async () => {
        const cfg = await api.config();
        const blob = new Blob([JSON.stringify(cfg, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "solar-config.json";
        a.click();
        URL.revokeObjectURL(a.href);
      },
      "ui.settings.toastExportConfigLoading",
      "ui.settings.toastExportConfigSuccess",
    );
  }

  private importConfig(e: Event): void {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () =>
      void this.toastRun(
        async () => {
          const data = JSON.parse(String(reader.result));
          const res = await api.putConfig(data);
          if (!res.ok) throw new Error(res.error || t("ui.settings.importFailed"));
        },
        "ui.settings.toastImportConfigLoading",
        "ui.settings.toastImportConfigSuccess",
      );
    reader.readAsText(file);
  }

  private async exportModel(): Promise<void> {
    await this.toastRun(
      async () => {
        const model = await api.exportModel();
        const blob = new Blob([JSON.stringify(model, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "solar-model.json";
        a.click();
        URL.revokeObjectURL(a.href);
      },
      "ui.settings.toastExportModelLoading",
      "ui.settings.toastExportModelSuccess",
    );
  }

  private importModel(e: Event): void {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () =>
      void this.toastRun(
        async () => {
          const data = JSON.parse(String(reader.result));
          const res = await api.importModel(data);
          if (!res.ok) throw new Error(t("ui.settings.importFailed"));
        },
        "ui.settings.toastImportModelLoading",
        "ui.settings.toastImportModelSuccess",
      );
    reader.readAsText(file);
  }

  private async retrainModel(): Promise<void> {
    await this.toastRun(
      async () => {
        const res = await api.retrainModel();
        if (!res.ok) throw new Error(t("ui.settings.retrainFailed"));
        if (!res.trained) {
          throw new Error(t("ui.settings.insufficientTelemetry"));
        }
      },
      "ui.settings.toastRetrainLoading",
      "ui.settings.toastRetrainSuccess",
    );
  }

  private async run(
    fn: () => Promise<void>,
    loading: string,
    success: string,
    _errorFallback?: string,
  ): Promise<void> {
    this.busy = true;
    const ok = await runWithToast(fn, { loading, success });
    if (ok) {
      await this.loadConfig();
      this.requestEntityReload();
    }
    this.busy = false;
  }

  private lbl(section: string, key: string) {
    return labelWithTip(fieldLabel(section, key), fieldHelp(section, key));
  }

  private renderSectionFields(name: string): unknown {
    const draftRec = this.draft as unknown as Record<string, Section> | null;
    const sec = draftRec?.[name];
    if (!sec) return null;
    const entries = Object.entries(sec).filter(
      ([k, v]) => isScalar(v) && !HIDDEN_FIELDS.has(k),
    );
    return html`
      <div class="fields">
        ${entries.map(([key, v]) => this.renderField(name, key, v as number | string | boolean))}
      </div>
    `;
  }

  private renderSectionPanel(
    title: string,
    help: string | undefined,
    content: unknown,
    badge: "server" | "browser" | "immediate" = "server",
  ) {
    return html`
      <div class="section-panel">
        <h4>
          ${title}
          ${this.persistenceBadge(badge)}
          ${help ? html`<solar-info-tip .text=${help}></solar-info-tip>` : null}
        </h4>
        ${content}
      </div>
    `;
  }

  private renderField(section: string, key: string, value: number | string | boolean) {
    const label = this.lbl(section, key);
    if (section === "site" && key === "timezone") {
      const tzValue = String(value);
      const resolved =
        tzValue.toLowerCase() === "auto"
          ? this.status?.timezone_resolved ?? ""
          : "";
      return html`<div class="field">
        <label>${label}</label>
        <solar-timezone-input
          .value=${String(value)}
          .resolvedHint=${resolved}
          @timezone-change=${(e: CustomEvent<string>) =>
            this.setField(section, key, e.detail)}
        />
      </div>`;
    }
    if (section === "forecast" && key === "provider") {
      return html`<div class="field">
        <label>${label}</label>
        <select
          .value=${String(value)}
          @change=${(e: Event) =>
            this.setField(section, key, (e.target as HTMLSelectElement).value)}
        >
          <option value="open-meteo">${t("ui.settings.openMeteo")}</option>
          <option value="solcast">${t("ui.settings.solcast")}</option>
        </select>
      </div>`;
    }
    if (typeof value === "boolean") {
      return html`<div class="field checkbox-row">
        <label>${label}</label>
        <input type="checkbox" .checked=${value}
          @change=${(e: Event) => this.setField(section, key, (e.target as HTMLInputElement).checked)} />
      </div>`;
    }
    if (typeof value === "number") {
      return html`<div class="field">
        <label>${label}</label>
        <input type="number" step="any" .value=${String(value)}
          @input=${(e: Event) => this.setField(section, key, Number((e.target as HTMLInputElement).value))} />
      </div>`;
    }
    return html`<div class="field">
      <label>${label}</label>
      <input type="text" .value=${value}
        @input=${(e: Event) => this.setField(section, key, (e.target as HTMLInputElement).value)} />
    </div>`;
  }

  // ----------------------------------------------------------- entity fields --
  private entityInput(section: string, group: string, key: string, domain: string) {
    const d = this.draft as unknown as Record<string, any>;
    const value = (d[section]?.[group]?.[key] ?? "") as string;
    return html`<div class="field">
      <label>${labelWithTip(entityLabel(key), entityHelp(key))}</label>
      <solar-entity-input
        .entityId=${value}
        .entities=${this.entities}
        .domains=${[domain]}
        placeholder=${`${domain}.…`}
        @entity-id-change=${(e: CustomEvent<string | null>) =>
          this.setNested(section, group, key, e.detail)}
      />
    </div>`;
  }

  private renderBatteryPowerReadRow(read: Record<string, unknown>) {
    const d = this.draft as unknown as Record<string, any>;
    const inv = (d.inverter ?? {}) as Record<string, unknown>;
    const value = (read.battery_power ?? "") as string;
    const invert = Boolean(inv.invert_battery_power);
    return html`
      <div class="field">
        <label>${labelWithTip(entityLabel("battery_power"), entityHelp("battery_power"))}</label>
        <solar-entity-input
          .entityId=${value}
          .entities=${this.entities}
          .domains=${["sensor"]}
          placeholder="sensor.…"
          @entity-id-change=${(e: CustomEvent<string | null>) =>
            this.setNested("inverter", "read", "battery_power", e.detail)}
        />
      </div>
      <div class="field checkbox-row" style="grid-column: 1 / -1">
        <label>
          <input
            type="checkbox"
            .checked=${invert}
            @change=${(e: Event) => this.setInverterFlag("invert_battery_power", (e.target as HTMLInputElement).checked)}
          />
          ${labelWithTip(
            t("ui.settings.invertBatteryPower"),
            t("ui.settings.invertBatteryHelp"),
          )}
        </label>
      </div>
    `;
  }

  private setInverterFlag(key: string, value: boolean): void {
    this.patchDraft((draft) => {
      const inv = { ...((draft.inverter ?? {}) as Record<string, unknown>), [key]: value };
      draft.inverter = inv;
    });
  }

  private renderLoadSheddingLink() {
    const ls = (this.draft as Record<string, unknown> | null)?.load_shedding as Record<string, unknown> | undefined;
    const tiers = (ls?.tiers ?? []) as unknown[];
    const enabled = Boolean(ls?.enabled);
    const summary = t("ui.loadShedding.settingsSummary", {
      count: String(tiers.length),
      state: enabled ? t("ui.loadShedding.settingsEnabled") : t("ui.loadShedding.settingsDisabled"),
    });
    return html`
      <div class="link-card">
        <div>
          <strong>${t("ui.settings.loadSheddingTitle")}</strong>
          <p class="label" style="margin:4px 0 0">${t("ui.settings.loadSheddingIntro")}</p>
          <p class="label" style="margin:4px 0 0">${summary}</p>
        </div>
        <button type="button" @click=${() => this.openLoadSheddingTab()}>
          ${t("ui.settings.openLoadShedding")} →
        </button>
      </div>
    `;
  }

  private renderHaSection() {
    const isAddon = Boolean(this.session?.is_addon);
    return html`
      ${this.renderHaControlsCard(isAddon)}
      ${this.renderHaIntegrationCard(isAddon)}
    `;
  }

  private haWsStatusMessage(): string {
    if (this.haConnected && !this.haWsCircuitOpen && !this.haWsErrorClass) {
      return t("ui.settings.haWsStatusOk");
    }
    if (this.haWsErrorClass === "banned_or_forbidden") {
      return t("ui.settings.haWsStatusBanned");
    }
    if (this.haWsErrorClass === "auth_invalid") {
      return t("ui.settings.haWsStatusAuth");
    }
    if (this.haWsCircuitOpen) {
      return t("ui.settings.haWsStatusCircuit");
    }
    if (this.haWsErrorClass === "transient") {
      return t("ui.settings.haWsStatusTransient");
    }
    return t("ui.settings.haWsStatusTransient");
  }

  private renderHaWsDiagnostics() {
    return html`
      <p class="label">
        ${this.haAuthMode
          ? t("ui.settings.haAuthMode", { mode: this.haAuthMode })
          : nothing}
      </p>
      <p class="label">${this.haWsStatusMessage()}</p>
      ${this.haWsLastError
        ? html`<p class="label" style="font-family:monospace;font-size:0.85em">${this.haWsLastError}</p>`
        : nothing}
      <div class="buttons">
        <button
          type="button"
          ?disabled=${this.haRetryBusy}
          @click=${() => void this.retryHaConnection()}
        >
          ${t("ui.settings.haWsRetry")}
        </button>
      </div>
    `;
  }

  private renderHaControlsCard(isAddon: boolean) {
    const d = this.draft as unknown as Record<string, any>;
    const ha = (d.ha ?? {}) as Record<string, unknown>;
    if (isAddon) {
      return this.renderSectionPanel(
        t("ui.settings.haControlsTitle"),
        t("ui.settings.haControlsIntro"),
        html`
          <p class="label">${t("ui.settings.haControlsAddonStatus")}</p>
          ${this.renderHaWsDiagnostics()}
        `,
        "immediate",
      );
    }
    return this.renderSectionPanel(
      t("ui.settings.haControlsTitle"),
      t("ui.settings.haControlsIntro"),
      html`
        ${this.renderHaWsDiagnostics()}
        ${this.renderSectionPanel(
          t("ui.settings.haOauthTitle"),
          t("ui.settings.haOauthIntro"),
          html`
            <p class="label">
              ${this.haOauthConnected
                ? this.haOauthDegraded
                  ? t("ui.settings.haOauthDegraded")
                  : t("ui.settings.haOauthConnected")
                : t("ui.settings.haOauthDisconnectedStatus")}
            </p>
            <div class="buttons">
              <button
                type="button"
                ?disabled=${this.haOauthBusy}
                @click=${() => void this.startHaOauth()}
              >
                ${t("ui.settings.haOauthConnect")}
              </button>
              <button
                type="button"
                ?disabled=${this.haOauthBusy || !this.haOauthConnected}
                @click=${() => void this.refreshHaOauthStatus()}
              >
                ${t("ui.settings.pairRefresh")}
              </button>
              <button
                type="button"
                ?disabled=${this.haOauthBusy || !this.haOauthConnected}
                @click=${() => void this.disconnectHaOauth()}
              >
                ${t("ui.settings.haOauthDisconnect")}
              </button>
            </div>
          `,
          "immediate",
        )}
        <div class="fields" style="margin-top:1rem">
          ${this.renderField("ha", "base_url", String(ha.base_url ?? ""))}
          ${typeof ha.verify_ssl === "boolean"
            ? this.renderField("ha", "verify_ssl", ha.verify_ssl)
            : null}
        </div>
        <p class="label">${t("ui.settings.haEnvTokenHint")}</p>
      `,
    );
  }

  private renderHaIntegrationCard(isAddon: boolean) {
    // Phase 5: on add-on, pairing is fallback-only (collapsed note + optional details).
    if (isAddon) {
      return this.renderSectionPanel(
        t("ui.settings.haIntegrationTitle"),
        t("ui.settings.haIntegrationIntro"),
        html`
          <p class="label">${t("ui.settings.haIntegrationAddonNote")}</p>
          <details style="margin-top:0.75rem">
            <summary>${t("ui.settings.pairTitle")}</summary>
            ${this.renderPairingBody()}
          </details>
        `,
        "immediate",
      );
    }
    return this.renderSectionPanel(
      t("ui.settings.haIntegrationTitle"),
      t("ui.settings.haIntegrationIntro"),
      this.renderPairingBody(),
      "immediate",
    );
  }

  private renderPairingBody() {
    return html`
      <p class="label">${t("ui.settings.pairHint")}</p>
      ${this.pairCode
        ? html`
            <p style="font-size:1.75rem;letter-spacing:0.12em;font-weight:700">
              ${this.pairCode}
            </p>
            <p class="label">
              ${t("ui.settings.pairExpires", { seconds: String(this.pairExpiresIn) })}
            </p>
            <div class="buttons">
              <button type="button" ?disabled=${this.pairBusy} @click=${() => void this.cancelPairing()}>
                ${t("ui.settings.pairCancel")}
              </button>
            </div>
          `
        : html`
            <div class="buttons">
              <button type="button" ?disabled=${this.pairBusy} @click=${() => void this.startPairing()}>
                ${t("ui.settings.pairGenerate")}
              </button>
              <button type="button" ?disabled=${this.pairBusy} @click=${() => void this.refreshPairStatus()}>
                ${t("ui.settings.pairRefresh")}
              </button>
            </div>
          `}
      ${this.pairClients.length
        ? html`
            <ul style="list-style:none;padding:0;margin:1rem 0 0">
              ${this.pairClients.map(
                (c) => html`
                  <li
                    style="display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid var(--border)"
                  >
                    <span>
                      <strong>${c.name}</strong>
                      <span class="label"> ${c.id}</span>
                    </span>
                    <button
                      type="button"
                      ?disabled=${this.pairBusy}
                      @click=${() => void this.revokePairClient(c.id)}
                    >
                      ${t("ui.settings.pairRevoke")}
                    </button>
                  </li>
                `,
              )}
            </ul>
          `
        : html`<p class="label">${t("ui.settings.pairNoClients")}</p>`}
    `;
  }

  private async refreshPairStatus(): Promise<void> {
    try {
      const status = await api.pairStatus();
      this.pairClients = status.clients ?? [];
      if (status.pending) {
        this.pairExpiresIn = status.pending.expires_in;
      } else if (!this.pairCode) {
        this.pairExpiresIn = 0;
      }
    } catch {
      /* optional until backend deployed */
    }
  }

  private async refreshHaConnectionHealth(): Promise<void> {
    try {
      const h = await api.haConnectionHealth();
      this.haConnected = Boolean(h.ha_connected);
      this.haAuthMode = h.ha_auth_mode ?? null;
      this.haWsErrorClass = h.ha_ws_error_class ?? null;
      this.haWsLastError = h.ha_ws_last_error ?? null;
      this.haWsCircuitOpen = Boolean(h.ha_ws_circuit_open);
    } catch {
      /* optional */
    }
  }

  private async retryHaConnection(): Promise<void> {
    this.haRetryBusy = true;
    try {
      const res = await api.haRetryConnection();
      this.haAuthMode = res.ha_auth_mode;
      this.haWsErrorClass = res.ha_ws_error_class;
      this.haWsLastError = res.ha_ws_last_error;
      this.haWsCircuitOpen = res.ha_ws_circuit_open;
      this.haConnected = res.rest_reachable;
      showToast({ message: t("ui.settings.haWsRetryOk"), variant: "success" });
      await this.refreshHaConnectionHealth();
    } catch (e) {
      showToast({
        message: e instanceof Error ? e.message : t("ui.settings.haWsRetryFailed"),
        variant: "error",
      });
    } finally {
      this.haRetryBusy = false;
    }
  }

  private async refreshHaOauthStatus(): Promise<void> {
    if (this.session?.is_addon) {
      this.haOauthConnected = false;
      this.haOauthDegraded = false;
      await this.refreshHaConnectionHealth();
      return;
    }
    try {
      const status = await api.haOauthStatus();
      this.haOauthConnected = status.connected;
      this.haOauthDegraded = status.degraded;
    } catch {
      /* optional until backend deployed */
    }
    await this.refreshHaConnectionHealth();
  }

  private async startPairing(): Promise<void> {
    this.pairBusy = true;
    try {
      const started = await api.pairStart();
      this.pairCode = started.code;
      this.pairExpiresIn = started.expires_in;
      showToast({ message: t("ui.settings.pairCodeIssued"), variant: "success" });
      await this.refreshPairStatus();
    } catch (e) {
      showToast({
        message: e instanceof Error ? e.message : t("ui.settings.pairFailed"),
        variant: "error",
      });
    } finally {
      this.pairBusy = false;
    }
  }

  private async cancelPairing(): Promise<void> {
    this.pairBusy = true;
    try {
      await api.pairCancel();
      this.pairCode = null;
      this.pairExpiresIn = 0;
      await this.refreshPairStatus();
    } finally {
      this.pairBusy = false;
    }
  }

  private async revokePairClient(id: string): Promise<void> {
    this.pairBusy = true;
    try {
      await api.pairRevoke(id);
      await this.refreshPairStatus();
      showToast({ message: t("ui.settings.pairClientRevoked"), variant: "success" });
    } catch (e) {
      showToast({
        message: e instanceof Error ? e.message : t("ui.settings.pairFailed"),
        variant: "error",
      });
    } finally {
      this.pairBusy = false;
    }
  }

  private async startHaOauth(): Promise<void> {
    this.haOauthBusy = true;
    try {
      const d = this.draft as unknown as Record<string, any> | null;
      const ha = (d?.ha as Record<string, unknown> | undefined) ?? {};
      const haUrl = String(ha.base_url ?? "").trim();
      const verifySsl = typeof ha.verify_ssl === "boolean" ? ha.verify_ssl : undefined;
      const publicBase = `${window.location.origin}${getBase()}`;
      const started = await api.haOauthStart(publicBase, haUrl || undefined, verifySsl);
      window.open(started.authorize_url, "_blank", "noopener,noreferrer");
      showToast({ message: t("ui.settings.haOauthWindowOpened"), variant: "success" });
      void this.pollHaOauthAfterAuthorize();
    } catch (e) {
      showToast({
        message: e instanceof Error ? e.message : t("ui.settings.haOauthFailed"),
        variant: "error",
      });
    } finally {
      this.haOauthBusy = false;
    }
  }

  /** Poll status after authorize popup so WS health updates once callback reconnects. */
  private async pollHaOauthAfterAuthorize(): Promise<void> {
    for (let i = 0; i < 90; i++) {
      await new Promise((r) => setTimeout(r, 2000));
      await this.refreshHaOauthStatus();
      if (
        this.haOauthConnected &&
        this.haConnected &&
        !this.haWsCircuitOpen &&
        this.haWsErrorClass !== "auth_invalid"
      ) {
        return;
      }
    }
  }

  private async disconnectHaOauth(): Promise<void> {
    this.haOauthBusy = true;
    try {
      await api.haOauthDisconnect();
      this.haOauthConnected = false;
      this.haOauthDegraded = false;
      showToast({ message: t("ui.settings.haOauthDisconnected"), variant: "success" });
      await this.refreshHaConnectionHealth();
    } catch (e) {
      showToast({
        message: e instanceof Error ? e.message : t("ui.settings.haOauthFailed"),
        variant: "error",
      });
    } finally {
      this.haOauthBusy = false;
    }
  }

  private renderDisplayPreferencesSection() {
    return this.renderSectionPanel(
      t("display.preferences"),
      t("display.preferencesIntro"),
      html`
        <div class="fields">
          <div class="field">
            <label>${t("display.language")}</label>
            <select
              .value=${this.locale}
              @change=${async (e: Event) => {
                const v = (e.target as HTMLSelectElement).value as AppLocale;
                this.locale = v;
                await setLocale(v);
              }}
            >
              ${LOCALES.map(
                (loc) => html`<option value=${loc.id}>${loc.nativeName}</option>`,
              )}
            </select>
          </div>
          <div class="field">
            <label>${t("display.dateFormat")}</label>
            <select
              .value=${this.dateFormat}
              @change=${(e: Event) => {
                const v = (e.target as HTMLSelectElement).value as DateDisplayFormat;
                this.dateFormat = v;
                setDateFormat(v);
              }}
            >
              <option value="locale">${t("display.dateLocale")}</option>
              <option value="ddmmyy">${t("display.dateDdmmyy")}</option>
              <option value="iso">${t("display.dateIso")}</option>
            </select>
          </div>
        </div>
      `,
      "browser",
    );
  }

  private renderSecuritySection() {
    return this.renderSectionPanel(
      t("ui.settings.securityTitle"),
      t("ui.settings.apiSecurityIntro"),
      html`
        ${this.session?.auth_mode === "local"
          ? html`
              <p class="label">
                ${t("ui.settings.signedInAs")}
                <strong>${this.session.display_name ?? this.session.username}</strong>.
              </p>
              <div class="buttons">
                <button
                  type="button"
                  @click=${async () => {
                    await api.logout();
                    window.dispatchEvent(new Event("solar-logout"));
                  }}
                >
                  ${t("ui.settings.signOut")}
                </button>
              </div>
            `
          : null}
        <div class="fields">
          <div class="field" style="grid-column: 1 / -1">
            <label>${labelWithTip("API token", fieldHelp("security", "api_token"))}</label>
            <input
              type="password"
              placeholder=${t("ui.settings.apiTokenPlaceholder")}
              .value=${this.apiToken}
              @input=${(e: Event) => {
                this.apiToken = (e.target as HTMLInputElement).value;
                setApiToken(this.apiToken.trim());
              }}
            />
          </div>
        </div>
      `,
      "browser",
    );
  }

  private mcpStatusPillClass(): string {
    const h = this.mcpHealth;
    if (!h?.mcp_enabled) return "mcp-status-pill";
    if (h.mcp_http_mounted) return "mcp-status-pill active";
    return "mcp-status-pill warn";
  }

  private mcpStatusLabel(): string {
    const h = this.mcpHealth;
    if (!h) return t("ui.settings.mcp.statusLoading");
    if (!h.mcp_enabled) return t("ui.settings.mcp.statusDisabled");
    if (h.mcp_http_mounted) return t("ui.settings.mcp.statusActive");
    return t("ui.settings.mcp.statusMisconfigured");
  }

  private renderMcpDeploymentNote() {
    if (this.session?.is_addon) {
      return html`
        <div class="link-card">
          <div>
            <strong>${t("ui.settings.mcp.haAddonTitle")}</strong>
            <p class="label" style="margin:4px 0 0">${t("ui.settings.mcp.haAddonIntro")}</p>
          </div>
        </div>
      `;
    }
    return html`
      <details>
        <summary>${t("ui.settings.mcp.envVarsTitle")}</summary>
        <p class="label">${t("ui.settings.mcp.envVarsIntro")}</p>
        <table class="env-table">
          <thead>
            <tr>
              <th>${t("ui.settings.mcp.envVarCol")}</th>
              <th>${t("ui.settings.mcp.envPurposeCol")}</th>
            </tr>
          </thead>
          <tbody>
            <tr><td><code>MCP_ENABLED</code></td><td>${t("ui.settings.mcp.envEnabled")}</td></tr>
            <tr><td><code>MCP_TOKEN</code></td><td>${t("ui.settings.mcp.envToken")}</td></tr>
            <tr><td><code>MCP_HTTP_PATH</code></td><td>${t("ui.settings.mcp.envPath")}</td></tr>
            <tr><td><code>SOLAR_API_URL</code></td><td>${t("ui.settings.mcp.envApiUrl")}</td></tr>
          </tbody>
        </table>
        <p class="label">${t("ui.settings.mcp.restartNote")}</p>
      </details>
    `;
  }

  private renderMcpSection() {
    const h = this.mcpHealth;
    const s = this.mcpSettings;
    const httpOpen = Boolean(h?.mcp_enabled || s?.enabled || this.mcpDraftEnabled);
    const editable = Boolean(s?.editable);
    return html`
      ${this.renderSectionPanel(
        t("ui.settings.mcp.statusTitle"),
        sectionHelp("mcp"),
        html`
          <p class="label">
            <span class=${this.mcpStatusPillClass()}>${this.mcpStatusLabel()}</span>
          </p>
          <p class="label">${editable ? t("ui.settings.mcp.envPersistenceNoteEditable") : t("ui.settings.mcp.envPersistenceNote")}</p>
          ${this.mcpPendingRestart
            ? html`<div class="mcp-pending-banner" role="status">${t("ui.settings.mcp.pendingRestartBanner")}</div>`
            : null}
          ${h
            ? html`
                <ul class="label" style="margin:8px 0 0;padding-inline-start:1.2em">
                  <li>
                    ${h.mcp_enabled
                      ? t("ui.settings.mcp.lineHttpEnabled")
                      : t("ui.settings.mcp.lineHttpDisabled")}
                  </li>
                  <li>
                    ${h.mcp_auth_configured
                      ? t("ui.settings.mcp.lineAuthOk")
                      : t("ui.settings.mcp.lineAuthMissing")}
                  </li>
                  ${h.mcp_tool_calls_total != null
                    ? html`<li>${t("ui.settings.mcp.lineToolCalls", { count: String(h.mcp_tool_calls_total) })}</li>`
                    : null}
                  ${h.mcp_auth_failures_total
                    ? html`<li style="color:var(--warn)">${t("ui.settings.mcp.lineAuthFailures", { count: String(h.mcp_auth_failures_total) })}</li>`
                    : null}
                </ul>
              `
            : html`<p class="label">${t("ui.settings.mcp.statusLoading")}</p>`}
        `,
      )}
      ${editable
        ? this.renderSectionPanel(
            t("ui.settings.mcp.configTitle"),
            undefined,
            html`
              <div class="fields">
                <label class="check">
                  <input
                    type="checkbox"
                    .checked=${this.mcpDraftEnabled}
                    ?disabled=${this.mcpBusy}
                    @change=${(e: Event) => {
                      this.mcpDraftEnabled = (e.target as HTMLInputElement).checked;
                    }}
                  />
                  ${t("ui.settings.mcp.enableLabel")}
                </label>
                <div class="field" style="grid-column:1/-1">
                  <label>${t("ui.settings.mcp.tokenLabel")}</label>
                  <input
                    type="password"
                    autocomplete="new-password"
                    placeholder=${s?.has_token
                      ? t("ui.settings.mcp.tokenConfiguredPlaceholder")
                      : t("ui.settings.mcp.tokenPlaceholder")}
                    .value=${this.mcpDraftToken}
                    ?disabled=${this.mcpBusy}
                    @input=${(e: Event) => {
                      this.mcpDraftToken = (e.target as HTMLInputElement).value;
                      this.mcpTokenDirty = true;
                    }}
                  />
                  <p class="label">${t("ui.settings.mcp.tokenHint")}</p>
                </div>
              </div>
              ${this.mcpGeneratedToken
                ? html`<p class="label" role="status">${t("ui.settings.mcp.generatedTokenNote")}: <code>${this.mcpGeneratedToken}</code></p>`
                : null}
              <div class="buttons">
                <button
                  type="button"
                  class="primary"
                  ?disabled=${this.mcpBusy}
                  @click=${() => void this.saveMcpSettings()}
                >
                  ${t("ui.settings.mcp.saveMcp")}
                </button>
                <button
                  type="button"
                  ?disabled=${this.mcpBusy}
                  @click=${() => void this.saveMcpSettings({ generate: true })}
                >
                  ${t("ui.settings.mcp.generateToken")}
                </button>
                <button
                  type="button"
                  ?disabled=${this.mcpBusy || !s?.has_token}
                  @click=${() => void this.saveMcpSettings({ clearToken: true })}
                >
                  ${t("ui.settings.mcp.clearToken")}
                </button>
              </div>
            `,
          )
        : null}
      ${this.renderSectionPanel(
        t("ui.settings.mcp.securityTitle"),
        undefined,
        html`
          <p class="label">${t("ui.settings.mcp.securityIntro")}</p>
          ${h?.mcp_enabled && !h.mcp_http_mounted
            ? html`<p class="label err" role="alert">${t("ui.settings.mcp.misconfiguredAlert")}</p>`
            : null}
        `,
      )}
      <details ?open=${httpOpen}>
        <summary>${t("ui.settings.mcp.httpTitle")}</summary>
        <p class="label">${t("ui.settings.mcp.httpIntro")}</p>
        <div class="fields">
          <div class="field">
            <label>${t("ui.settings.mcp.httpPathLabel")}</label>
            <input type="text" readonly .value=${h?.mcp_http_path ?? "/mcp"} />
          </div>
          <div class="field" style="grid-column:1/-1">
            <label>${t("ui.settings.mcp.httpUrlLabel")}</label>
            <input
              type="text"
              readonly
              .value=${h?.mcp_http_url ?? t("ui.settings.mcp.httpUrlUnavailable")}
            />
          </div>
        </div>
        <div class="buttons">
          <button
            type="button"
            ?disabled=${!h?.mcp_http_url}
            @click=${() => void this.copyText(h!.mcp_http_url!, "ui.settings.mcp.copyUrlSuccess")}
          >
            ${t("ui.settings.mcp.copyUrl")}
          </button>
        </div>
        <p class="label">${t("ui.settings.mcp.httpBearerNote")}</p>
      </details>
      <details>
        <summary>${t("ui.settings.mcp.stdioTitle")}</summary>
        <ol class="label">
          <li>${t("ui.settings.mcp.stdioStep1")}</li>
          <li>${t("ui.settings.mcp.stdioStep2")}</li>
          <li>${t("ui.settings.mcp.stdioStep3")}</li>
          <li>${t("ui.settings.mcp.stdioStep4")}</li>
        </ol>
        <pre class="mcp-snippet">${MCP_STDIO_SNIPPET}</pre>
        <div class="buttons">
          <button
            type="button"
            @click=${() => void this.copyText(MCP_STDIO_SNIPPET, "ui.settings.mcp.copySnippetSuccess")}
          >
            ${t("ui.settings.mcp.copySnippet")}
          </button>
        </div>
        <p class="label">${t("ui.settings.mcp.docsHint")}</p>
      </details>
      ${this.renderMcpDeploymentNote()}
      <div class="link-card">
        <div>
          <strong>${t("ui.settings.mcp.relatedSecurityTitle")}</strong>
          <p class="label" style="margin:4px 0 0">${t("ui.settings.mcp.relatedSecurityIntro")}</p>
        </div>
        <button type="button" @click=${() => this.openApiSecuritySection()}>
          ${t("ui.settings.mcp.openApiSecurity")} →
        </button>
      </div>
    `;
  }

  private formatPublishedAt(iso: string | null): string {
    if (!iso) return "";
    return formatDateTime(iso, "iso");
  }

  private async refreshUpdateInfo(): Promise<void> {
    if (this.session?.is_addon) return;
    const toastId = "update-check";
    this.updateChecking = true;
    showToast({
      id: toastId,
      message: t("ui.settings.checkingUpdates"),
      variant: "loading",
      persistent: true,
    });
    try {
      const info = await api.updateInfo({ refresh: true });
      this.updateInfo = info;
      if (!info.update_failed) this.installRecoveryOffer = false;
      this.dispatchEvent(
        new CustomEvent("solar-update-info", { detail: info, bubbles: true, composed: true }),
      );
      dismissToast(toastId);
      if (!info.latest_version) {
        showToast({ message: t("ui.settings.checkUpdatesFailed"), variant: "error" });
      } else if (info.update_available) {
        showToast({
          message: t("ui.settings.updateVersionAvailable", {
            latest: info.latest_version,
            current: info.current_version ?? "",
          }),
          variant: "info",
        });
      } else {
        showToast({
          message: t("ui.settings.onLatest"),
          variant: "success",
        });
      }
    } catch (e) {
      dismissToast(toastId);
      showToast({
        message: e instanceof Error ? e.message : String(e),
        variant: "error",
      });
    } finally {
      this.updateChecking = false;
    }
  }

  private updateTimeoutMs(): number {
    return this.updateInfo?.deployment === "proxmox" ? 240_000 : 180_000;
  }

  private syncUpdateInfoFromPoll(info: UpdateInfo): void {
    if (this.session?.is_addon) return;
    this.updateInfo = info;
    if (info.update_progress) {
      this.updateProgress = info.update_progress;
    }
    this.dispatchEvent(
      new CustomEvent("solar-update-info", { detail: info, bubbles: true, composed: true }),
    );
  }

  private progressToastMessage(progress?: UpdateProgress | null, healthWait?: boolean): string {
    if (healthWait) return t("ui.settings.waitingRestart");
    if (!progress) return t("ui.settings.updateInProgress");
    let msg = stageLabel(progress.stage, progress);
    if (progress.stage === "pulling" && progress.pull_detail) {
      msg = `${msg} — ${progress.pull_detail}`;
    }
    return msg;
  }

  private async watchUpdateCompletion(opts: {
    toastId: string;
    targetVersion?: string;
  }): Promise<{ ok: boolean; failed?: { message: string; backup?: string | null } }> {
    const token = ++this.updateWatchToken;
    const deadline = Date.now() + this.updateTimeoutMs();
    let sawInProgress = false;
    let pollErrors = 0;

    while (Date.now() < deadline && token === this.updateWatchToken) {
      try {
        const info = await api.updateInfo();
        if (token !== this.updateWatchToken) return { ok: false };
        this.syncUpdateInfoFromPoll(info);
        if (info.update_failed) {
          return { ok: false, failed: info.update_failed };
        }
        if (info.update_in_progress) {
          sawInProgress = true;
          pollErrors = 0;
          this.updateHealthWait = false;
          updateToast(opts.toastId, {
            message: this.progressToastMessage(info.update_progress),
          });
          await new Promise((r) => setTimeout(r, 2000));
          continue;
        }
        if (sawInProgress || pollErrors > 0) {
          this.updateHealthWait = true;
          break;
        }
        await new Promise((r) => setTimeout(r, 2000));
      } catch {
        pollErrors += 1;
        if (sawInProgress) {
          this.updateHealthWait = true;
          break;
        }
        if (pollErrors >= 3) break;
        await new Promise((r) => setTimeout(r, 2000));
      }
    }

    this.updateHealthWait = true;
    const healthStart = Date.now();
    while (Date.now() < deadline && token === this.updateWatchToken) {
      const elapsed = Math.floor((Date.now() - healthStart) / 1000);
      updateToast(opts.toastId, {
        message: `Waiting for service to restart… (${elapsed}s)`,
      });
      await new Promise((r) => setTimeout(r, 3000));
      try {
        const h = await api.health();
        if (h.status !== "ok") continue;
        if (opts.targetVersion) {
          try {
            const info = await api.updateInfo();
            if (token !== this.updateWatchToken) return { ok: false };
            if (info.current_version && info.current_version !== opts.targetVersion) {
              continue;
            }
          } catch {
            /* service may still be starting API routes */
          }
        }
        return { ok: true };
      } catch {
        /* service restarting */
      }
    }
    return { ok: false };
  }

  private versionBelowMin(version: string, minVersion?: string): boolean {
    if (!minVersion) return false;
    const parse = (v: string) =>
      v.replace(/^v/i, "").split(".").map((n) => parseInt(n, 10) || 0);
    const a = parse(version);
    const b = parse(minVersion);
    for (let i = 0; i < 3; i++) {
      if ((a[i] ?? 0) < (b[i] ?? 0)) return true;
      if ((a[i] ?? 0) > (b[i] ?? 0)) return false;
    }
    return false;
  }

  private formatBackupSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  private toggleReleaseNotes(version: string): void {
    this.expandedRelease = this.expandedRelease === version ? null : version;
  }

  private async applyUpdate(version?: string): Promise<void> {
    if (this.session?.is_addon) return;
    const info = this.updateInfo;
    if (!info?.can_apply) return;
    const release = version
      ? info.releases?.find((r) => r.version === version)
      : info.releases?.find((r) => r.relation === "newer");
    const target = version ?? release?.version ?? info.latest_version;
    if (!target) return;
    if (release?.relation === "current") return;

    const isDowngrade = release?.relation === "older";
    const downgradeWarning = info.downgrade_warning ?? "";
    const schemaNote = isDowngrade ? `\n\n${SCHEMA_DOWNGRADE_NOTE}` : "";
    const betaNote = release?.prerelease ? `\n\n${t("ui.settings.betaInstallConfirm")}` : "";
    const confirmMsg = isDowngrade
      ? `Install v${target}? This is an older release.\n\n${downgradeWarning}${schemaNote}${betaNote}`
      : `Install v${target} now? The service will restart and this page may disconnect briefly.${betaNote}`;
    if (!window.confirm(confirmMsg)) return;

    const toastId = "update-apply";
    this.updateBusy = true;
    this.installRecoveryOffer = false;
    this.updateProgress = null;
    this.updateHealthWait = false;
    let reloaded = false;
    showToast({
      id: toastId,
      message: t("ui.settings.startingUpdate"),
      variant: "loading",
      persistent: true,
    });
    try {
      await api.applyUpdate(target);
      const result = await this.watchUpdateCompletion({ toastId, targetVersion: target });
      if (result.failed) {
        dismissToast(toastId);
        showToast({
          message: result.failed.message,
          variant: "error",
          persistent: true,
        });
        this.installRecoveryOffer = true;
      } else if (result.ok) {
        updateToast(toastId, { message: t("ui.settings.updateCompleteReload"), variant: "success" });
        reloaded = true;
        window.location.reload();
      } else {
        this.installRecoveryOffer = true;
        dismissToast(toastId);
        showToast({
          message: t("ui.settings.updateStartedTimeout"),
          variant: "error",
          persistent: true,
        });
      }
    } catch (e) {
      dismissToast(toastId);
      showToast({
        message: e instanceof Error ? e.message : String(e),
        variant: "error",
        persistent: true,
      });
    } finally {
      this.updateBusy = false;
      this.updateHealthWait = false;
      if (!reloaded) void this.refreshUpdateInfo();
    }
  }

  private async restoreBackup(backupName?: string): Promise<void> {
    if (this.session?.is_addon) return;
    const info = this.updateInfo;
    if (!info?.can_apply) return;
    const name = backupName ?? info.backups?.[0]?.name;
    if (!name) return;
    if (
      !window.confirm(
        `Restore backup ${name}? This overwrites current /app/data and restarts the service.`,
      )
    ) {
      return;
    }
    const toastId = "update-restore";
    this.updateBusy = true;
    this.installRecoveryOffer = false;
    this.updateProgress = null;
    this.updateHealthWait = false;
    let reloaded = false;
    showToast({
      id: toastId,
      message: t("ui.settings.startingRestore"),
      variant: "loading",
      persistent: true,
    });
    try {
      await api.restoreUpdateBackup(name);
      const result = await this.watchUpdateCompletion({ toastId });
      if (result.failed) {
        dismissToast(toastId);
        showToast({
          message: result.failed.message,
          variant: "error",
          persistent: true,
        });
      } else if (result.ok) {
        updateToast(toastId, { message: t("ui.settings.restoreCompleteReload"), variant: "success" });
        reloaded = true;
        window.location.reload();
      } else {
        dismissToast(toastId);
        showToast({
          message: t("ui.settings.restoreTimeout"),
          variant: "error",
          persistent: true,
        });
      }
    } catch (e) {
      dismissToast(toastId);
      showToast({
        message: e instanceof Error ? e.message : String(e),
        variant: "error",
        persistent: true,
      });
    } finally {
      this.updateBusy = false;
      this.updateHealthWait = false;
      if (!reloaded) void this.refreshUpdateInfo();
    }
  }

  private recoveryBackupName(): string | undefined {
    const failed = this.updateInfo?.update_failed;
    if (failed?.backup) {
      const name = failed.backup.split("/").pop();
      if (name) return name;
    }
    return this.updateInfo?.backups?.[0]?.name;
  }

  private renderUpdateProgress() {
    const progress = this.updateProgress ?? this.updateInfo?.update_progress ?? null;
    const failed = this.updateInfo?.update_failed;
    const inProgress = Boolean(this.updateInfo?.update_in_progress) || this.updateBusy;
    if (!inProgress && !progress && !failed) return null;

    const operation = progress?.operation ?? "update";
    const stages = flowStages(operation);
    const failedActive = Boolean(failed) && !inProgress;
    const activeIdx = failedActive
      ? stages.length
      : activeStageIndex(
          stages,
          progress,
          this.updateHealthWait,
          Boolean(this.updateInfo?.update_in_progress),
        );
    const activeStage = failedActive
      ? "failed"
      : this.updateHealthWait
        ? null
        : (progress?.stage ?? (this.updateInfo?.update_in_progress ? "starting" : null));

    return html`
      <div class="update-progress">
        <h4>${progressHeaderTitle(progress, this.updateHealthWait)}</h4>
        ${stages.map((stage, idx) => {
          const done = idx < activeIdx;
          const active = !failedActive && !this.updateHealthWait && activeStage === stage;
          const showPullBar =
            active && progress?.stage === "pulling" && progress.pull_percent != null;
          return html`
            <div class="update-step ${done ? "done" : ""} ${active ? "active" : ""}">
              <span class="update-step-icon">
                ${done ? "✓" : active ? html`<span class="update-spinner"></span>` : "·"}
              </span>
              <span>
                ${stageLabel(stage, active ? progress : null)}
                ${showPullBar
                  ? html`
                      <div
                        class="update-pull-track"
                        role="progressbar"
                        aria-valuemin="0"
                        aria-valuemax="100"
                        aria-valuenow=${progress!.pull_percent!}
                      >
                        <div
                          class="update-pull-bar"
                          style="width: ${progress!.pull_percent}%"
                        ></div>
                      </div>
                    `
                  : null}
                ${active && progress?.stage === "pulling" && progress.pull_detail
                  ? html`<span class="update-step-detail">${progress.pull_detail}</span>`
                  : null}
              </span>
            </div>
          `;
        })}
        ${failedActive
          ? html`
              <div class="update-step active">
                <span class="update-step-icon">✕</span>
                <span>${failed!.message}</span>
              </div>
            `
          : null}
        ${this.updateHealthWait
          ? html`
              <div class="update-step active">
                <span class="update-step-icon"><span class="update-spinner"></span></span>
                <span>Waiting for service to restart…</span>
              </div>
            `
          : null}
      </div>
    `;
  }

  private renderRecoveryBanner() {
    const failed = this.updateInfo?.update_failed;
    if (!failed && !this.installRecoveryOffer) return null;
    const backup = this.recoveryBackupName();
    const message =
      failed?.message ?? t("ui.settings.restoreHint");
    return html`
      <div class="recovery-banner">
        <p>${message}</p>
        <p class="label">${updateLogHint()}</p>
        ${backup
          ? html`
              <div class="buttons">
                <button
                  class="primary"
                  ?disabled=${this.updateBusy || Boolean(this.updateInfo?.update_in_progress)}
                  @click=${() => void this.restoreBackup(backup)}
                >
                  ${t("ui.settings.restoreLastBackup")}
                </button>
              </div>
            `
          : null}
      </div>
    `;
  }

  private async setIncludePrereleases(enabled: boolean): Promise<void> {
    if (this.session?.is_addon) return;
    if (this.updateChecking || this.updateBusy) return;
    try {
      await api.updatePreferences(enabled);
      await this.refreshUpdateInfo();
    } catch (e) {
      showToast({
        message: e instanceof Error ? e.message : String(e),
        variant: "error",
      });
    }
  }

  private renderReleaseRow(release: ReleaseSummary, info: UpdateInfo) {
    const minVer = info.min_self_update_version;
    const belowMin = this.versionBelowMin(release.version, minVer);
    const expanded = this.expandedRelease === release.version;
    const badge =
      release.relation === "current"
        ? html`<span class="release-badge current">${t("ui.settings.releaseCurrent")}</span>`
        : release.relation === "newer"
          ? html`<span class="release-badge newer">${t("ui.settings.releaseNewer")}</span>`
          : null;
    const prereleaseBadge = release.prerelease
      ? html`<span class="release-badge prerelease">${t("ui.settings.releasePrerelease")}</span>`
      : null;

    return html`
      <tr>
        <td>
          <strong>v${release.version}</strong>${badge}${prereleaseBadge}
          ${release.published_at
            ? html`<div class="label">${this.formatPublishedAt(release.published_at)}</div>`
            : null}
        </td>
        <td>
          ${release.release_notes
            ? html`
                <button type="button" class="link" @click=${() => this.toggleReleaseNotes(release.version)}>
                  ${expanded ? t("ui.settings.hideNotes") : t("ui.settings.showNotes")}
                </button>
                ${expanded
                  ? html`<div class="release-notes">${renderMarkdown(release.release_notes)}</div>`
                  : null}
              `
            : html`<span class="label">—</span>`}
          ${!info.can_apply && info.deployment !== "addon" && expanded && release.apply_instructions
            ? html`<pre class="upgrade-cmd">${release.apply_instructions}</pre>`
            : null}
        </td>
        <td>
          ${info.can_apply && release.installable
            ? html`
                <button
                  class=${release.relation === "newer" ? "primary" : ""}
                  ?disabled=${this.updateBusy || Boolean(info.update_in_progress) || belowMin}
                  title=${belowMin ? `Requires v${minVer}+ for one-click install` : ""}
                  @click=${() => void this.applyUpdate(release.version)}
                >
                  ${t("ui.settings.install")}
                </button>
              `
            : release.relation === "current"
              ? html`<span class="label">${t("ui.settings.running")}</span>`
              : belowMin
                ? html`<span class="label">${t("ui.settings.belowMin", { version: minVer ?? "" })}</span>`
                : info.deployment === "addon"
                  ? html`<span class="label">${t("ui.settings.useHaSupervisor")}</span>`
                  : null}
        </td>
      </tr>
    `;
  }

  private renderUpdatesSection() {
    const info = this.updateInfo;
    const current = info?.current_version ?? this.session?.version ?? "—";
    const latest = info?.latest_version;
    const releases = info?.releases ?? [];
    const upToDate = info && !info.update_available && latest;

    return this.renderSectionPanel(
      t("ui.settings.softwareUpdates"),
      undefined,
      html`
        <p class="label">
          ${t("ui.settings.runningVersion", { current })}
          ${info?.previous_version
            ? t("ui.settings.previouslyVersion", { previous: info.previous_version })
            : null}
          ${latest ? t("ui.settings.latestRelease", { latest }) : null}
        </p>
        ${upToDate
          ? html`<p class="label">${t("ui.settings.onLatest")}</p>`
          : info?.update_available
            ? html`<p class="label">${t("ui.settings.newerAvailable")}</p>`
            : releases.length
              ? null
              : html`<p class="label">${t("ui.settings.checkUpdatesFailed")}</p>`}
        ${info?.deployment === "addon"
          ? html`<p class="label">${t("ui.settings.haSupervisorNote")}</p>`
          : null}
        ${info?.deployment === "proxmox"
          ? html`<p class="label">${t("ui.settings.proxmoxNote")}</p>`
          : null}
        <label class="field" style="margin-top:10px">
          <span style="display:inline-flex;align-items:center;gap:6px">
            <input
              type="checkbox"
              .checked=${Boolean(info?.include_prereleases)}
              ?disabled=${this.updateChecking || this.updateBusy}
              @change=${(e: Event) => {
                const checked = (e.target as HTMLInputElement).checked;
                void this.setIncludePrereleases(checked);
              }}
            />
            ${t("ui.settings.includePrereleases")}
            <solar-info-tip .text=${t("ui.settings.includePrereleasesHelp")}></solar-info-tip>
          </span>
        </label>
        ${info?.update_available
          ? html`<span class="badge-update">${t("ui.settings.updateAvailableBadge", { version: latest ?? "" })}</span>`
          : null}
        ${this.renderUpdateProgress()}
        ${this.renderRecoveryBanner()}
        ${releases.length
          ? html`
              <table class="release-table">
                <thead>
                  <tr>
                    <th>${t("ui.settings.versionCol")}</th>
                    <th>${t("ui.settings.releaseNotesCol")}</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  ${releases.map((r) => this.renderReleaseRow(r, info!))}
                </tbody>
              </table>
            `
          : info?.release_notes
            ? html`<div class="release-notes">${renderMarkdown(info.release_notes)}</div>`
            : null}
        ${info?.can_apply
          ? null
          : info?.apply_instructions
            ? html`<pre class="upgrade-cmd">${info.apply_instructions}</pre>`
            : null}
        ${info?.can_apply && info.backups && info.backups.length
          ? html`
              <details style="margin-top:12px">
                <summary>${t("ui.settings.dataBackups", { count: String(info.backups.length) })}</summary>
                <p class="label">${t("ui.settings.backupsIntro")}</p>
                ${info.backups.map(
                  (b) => html`
                    <div class="row" style="margin:6px 0">
                      <span style="flex:1">
                        ${b.name}
                        <span class="label">
                          · ${this.formatPublishedAt(b.created_at)} · ${this.formatBackupSize(b.size_bytes)}
                        </span>
                      </span>
                      <button
                        type="button"
                        ?disabled=${this.updateBusy || Boolean(info.update_in_progress)}
                        @click=${() => void this.restoreBackup(b.name)}
                      >
                        ${t("ui.settings.restore")}
                      </button>
                    </div>
                  `,
                )}
              </details>
            `
          : null}
        <div class="buttons">
          <button
            type="button"
            ?disabled=${this.updateChecking || this.updateBusy}
            @click=${() => void this.refreshUpdateInfo()}
          >
            ${this.updateChecking ? t("ui.settings.checking") : t("ui.settings.checkUpdates")}
          </button>
          ${info?.can_apply
            ? html`<button
                type="button"
                ?disabled=${this.updateBusy || this.restartBusy || Boolean(info.update_in_progress)}
                title=${t("ui.settings.recreateHelp")}
                @click=${() => void this.recreateService()}
              >
                ${t("ui.settings.recreateContainer")}
              </button>`
            : null}
        </div>
        ${info?.can_apply
          ? html`<p class="label">${t("ui.settings.recreateHelp")}</p>`
          : null}
      `,
      "immediate",
    );
  }

  private renderSitePvSection() {
    const d = this.draft as unknown as Record<string, any>;
    const forecast = (d.forecast ?? {}) as Record<string, unknown>;
    const provider = String(forecast.provider ?? "open-meteo");
    const configured = this.status?.solcast_configured ?? false;
    return this.renderSectionPanel(
      t("ui.settings.nav.sitePv"),
      sectionHelp("site"),
      html`
        ${this.renderSectionFields("site")}
        ${typeof forecast.provider === "string" || forecast.provider === undefined
          ? this.renderField("forecast", "provider", String(forecast.provider ?? "open-meteo"))
          : null}
        ${provider === "solcast"
          ? html`<p class="label ${configured ? "" : "err"}">
              ${t("ui.settings.solcastEnvNote")}
              ${configured ? t("ui.settings.credentialsOk") : t("ui.settings.credentialsMissing")}
            </p>`
          : null}
        ${this.renderPvArraysInner()}
      `,
    );
  }

  private setArray(i: number, key: string, value: unknown): void {
    this.patchDraft((d) => {
      const arrays = (d.forecast?.arrays ?? []) as Record<string, unknown>[];
      arrays[i] = { ...arrays[i], [key]: value };
      d.forecast = { ...(d.forecast ?? {}), arrays };
    });
  }

  private addArray(): void {
    this.patchDraft((d) => {
      const arrays = [...((d.forecast?.arrays ?? []) as unknown[])];
      arrays.push({ name: "array", kwp: 5, tilt: 15, azimuth: 180 });
      d.forecast = { ...(d.forecast ?? {}), arrays };
    });
  }

  private removeArray(i: number): void {
    this.patchDraft((d) => {
      const arrays = [...((d.forecast?.arrays ?? []) as unknown[])];
      arrays.splice(i, 1);
      d.forecast = { ...(d.forecast ?? {}), arrays };
    });
  }

  private renderPvArraysInner() {
    const d = this.draft as unknown as Record<string, any>;
    const arrays = (d.forecast?.arrays ?? []) as Record<string, any>[];
    return html`
      <p class="label" style="margin-top:12px">
        ${t("ui.settings.pvArraysTitle")}
        <solar-info-tip .text=${sectionHelp("pv_arrays")!}></solar-info-tip>
      </p>
      <p class="label">${t("ui.settings.pvArraysIntro")}</p>
      ${arrays.map((a, i) => html`
        <div class="pv-array-card">
          <button
            type="button"
            class="pv-array-dismiss icon-btn"
            title=${t("ui.settings.removeArray")}
            @click=${() => this.removeArray(i)}
          >×</button>
          <div class="pv-array-title">${String(a.name ?? `Array ${i + 1}`)}</div>
          <div class="fields">
            <div class="field">
              <label>${labelWithTip(pvLabel("name"), pvHelp("name"))}</label>
              <input type="text" .value=${String(a.name ?? "")}
                @input=${(e: Event) => this.setArray(i, "name", (e.target as HTMLInputElement).value)} />
            </div>
            <div class="field">
              <label>${labelWithTip(pvLabel("kwp"), pvHelp("kwp"))}</label>
              <input type="number" step="any" .value=${String(a.kwp ?? "")}
                @input=${(e: Event) => this.setArray(i, "kwp", Number((e.target as HTMLInputElement).value))} />
            </div>
            <div class="field">
              <label>${labelWithTip(pvLabel("tilt"), pvHelp("tilt"))}</label>
              <input type="number" step="any" .value=${String(a.tilt ?? "")}
                @input=${(e: Event) => this.setArray(i, "tilt", Number((e.target as HTMLInputElement).value))} />
            </div>
            <div class="field">
              <label>${labelWithTip(pvLabel("azimuth"), pvHelp("azimuth"))}</label>
              <solar-azimuth-input
                .value=${Number(a.azimuth ?? 180)}
                @azimuth-change=${(e: CustomEvent<number>) => this.setArray(i, "azimuth", e.detail)}
              ></solar-azimuth-input>
            </div>
          </div>
        </div>
      `)}
      <div class="buttons">
        <button type="button" @click=${() => this.addArray()}>${t("ui.settings.addArray")}</button>
      </div>
    `;
  }

  private onPriorityDragStart(i: number): void {
    this.dragPriorityIndex = i;
  }

  private onPriorityDragOver(e: DragEvent): void {
    e.preventDefault();
  }

  private onPriorityDrop(targetIndex: number, e: DragEvent): void {
    e.preventDefault();
    const from = this.dragPriorityIndex;
    if (from == null || from === targetIndex) return;
    this.patchDraft((d) => {
      const list = this.priorityOrderFromDraft(d);
      const [item] = list.splice(from, 1);
      list.splice(targetIndex, 0, item);
      d.engine = { ...(d.engine ?? {}), priority_order: list };
    });
    this.dragPriorityIndex = null;
  }

  private setEngineMode(mode: string): void {
    this.setField("engine", "mode", mode);
  }

  private priorityOrderFromDraft(d: Record<string, unknown>): OptimizationPriorityKey[] {
    const raw = (d.engine as Record<string, unknown> | undefined)?.priority_order;
    if (!Array.isArray(raw) || raw.length === 0) {
      return [...DEFAULT_PRIORITY_ORDER];
    }
    const seen = new Set<string>();
    const out: OptimizationPriorityKey[] = [];
    for (const item of raw) {
      const key = String(item);
      if (!DEFAULT_PRIORITY_ORDER.includes(key as OptimizationPriorityKey)) continue;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(key as OptimizationPriorityKey);
    }
    for (const key of DEFAULT_PRIORITY_ORDER) {
      if (!seen.has(key)) out.push(key);
    }
    return out;
  }

  private priorityOrder(): OptimizationPriorityKey[] {
    if (!this.draft) return [...DEFAULT_PRIORITY_ORDER];
    return this.priorityOrderFromDraft(this.draft as unknown as Record<string, unknown>);
  }

  private movePriority(i: number, dir: -1 | 1): void {
    this.patchDraft((d) => {
      const list = this.priorityOrderFromDraft(d);
      const j = i + dir;
      if (j < 0 || j >= list.length) return;
      [list[i], list[j]] = [list[j], list[i]];
      d.engine = { ...(d.engine ?? {}), priority_order: list };
    });
  }

  private normalizePriorityOrderForSave(d: Record<string, any>): void {
    const eng = (d.engine ?? {}) as Record<string, unknown>;
    eng.priority_order = this.priorityOrderFromDraft(d);
    d.engine = eng;
  }

  private renderEngineSection() {
    const d = this.draft as unknown as Record<string, any>;
    const eng = (d.engine ?? {}) as Record<string, unknown>;
    const mode = String(eng.mode ?? "rules");
    return this.renderSectionPanel(
      sectionTitle("engine"),
      sectionHelp("engine"),
      html`
        <p class="label">${t("ui.settings.engineIntro")}</p>
        <div class="fields">
          <div class="field checkbox-row">
            <label>${this.lbl("engine", "enabled")}</label>
            <input
              type="checkbox"
              .checked=${eng.enabled !== false}
              @change=${(e: Event) =>
                this.setField("engine", "enabled", (e.target as HTMLInputElement).checked)}
            />
          </div>
          <div class="field">
            <label>${this.lbl("engine", "mode")}</label>
            <div class="mode-toggle" role="group">
              <button
                type="button"
                class=${mode === "rules" ? "active" : ""}
                @click=${() => this.setEngineMode("rules")}
              >${t("ui.settings.rulesMode")}</button>
              <button
                type="button"
                class=${mode === "mpc" ? "active" : ""}
                @click=${() => this.setEngineMode("mpc")}
              >${t("ui.settings.mpcMode")}</button>
            </div>
          </div>
          ${typeof eng.mpc_horizon_hours === "number"
            ? this.renderField("engine", "mpc_horizon_hours", eng.mpc_horizon_hours)
            : null}
        </div>
        <p class="label" style="margin-top:12px">${t("ui.settings.optimizationPriority")}</p>
        ${this.priorityOrder().map(
          (key, i) => html`
            <div
              class="priority-row ${this.dragPriorityIndex === i ? "dragging" : ""}"
              draggable="true"
              @dragstart=${() => this.onPriorityDragStart(i)}
              @dragover=${this.onPriorityDragOver}
              @drop=${(e: DragEvent) => this.onPriorityDrop(i, e)}
            >
              <span class="priority-handle" aria-hidden="true">≡</span>
              <span style="flex:1">
                ${labelWithTip(
                  `${i + 1}. ${optimizationPriorityLabel(key)}`,
                  priorityEffectHelp(key),
                )}
              </span>
              <button type="button" ?disabled=${i === 0} @click=${() => this.movePriority(i, -1)} aria-label="Move up">↑</button>
              <button
                type="button"
                ?disabled=${i === this.priorityOrder().length - 1}
                @click=${() => this.movePriority(i, 1)}
                aria-label="Move down"
              >↓</button>
            </div>
          `,
        )}
        ${eng.mode === "mpc" && !this.mpcAvailable
          ? html`<p class="label" style="color:var(--warn)">${t("ui.settings.mpcUnavailable")}</p>`
          : null}
        ${this.mlLoadEnabled && !this.mlAvailable
          ? html`<p class="label" style="color:var(--warn)">${t("ui.settings.mlUnavailable")}</p>`
          : null}
        <p class="label" style="margin-top:14px;font-weight:600">${sectionTitle("control")}</p>
        ${this.renderSectionFields("control")}
      `,
    );
  }

  private renderTemperature() {
    const d = this.draft as unknown as Record<string, any>;
    const temp = (d.forecast?.temperature ?? {}) as Record<string, any>;
    const num = (key: string) => html`<div class="field">
      <label>${this.lbl("temperature", key)}</label>
      <input type="number" step="any" .value=${String(temp[key] ?? "")}
        @input=${(e: Event) =>
          this.setNested("forecast", "temperature", key, Number((e.target as HTMLInputElement).value))} />
    </div>`;
    const bool = (key: string) => html`<div class="field checkbox-row">
      <label>${this.lbl("temperature", key)}</label>
      <input type="checkbox" .checked=${Boolean(temp[key])}
        @change=${(e: Event) =>
          this.setNested("forecast", "temperature", key, (e.target as HTMLInputElement).checked)} />
    </div>`;
    return this.renderSectionPanel(
      t("ui.settings.temperatureTitle"),
      sectionHelp("temperature"),
      html`
        <p class="label">${t("ui.settings.temperatureIntro")}</p>
        <div class="fields">
          ${bool("enabled")}
          ${this.entityInput("forecast", "temperature", "ha_entity", "sensor")}
          ${num("hdd_base_c")}
          ${num("cdd_base_c")}
          ${bool("use_month_fallback")}
          ${num("min_load_fraction")}
          ${num("training_days")}
        </div>
      `,
    );
  }

  private renderInverterMap() {
    const d = this.draft as unknown as Record<string, any>;
    const read = (d.inverter?.read ?? {}) as Record<string, unknown>;
    return this.renderSectionPanel(
      t("ui.settings.inverterMapTitle"),
      sectionHelp("inverter"),
      html`
        <p class="label">
          ${this.entitiesConnected
            ? t("ui.settings.inverterConnectedHint")
            : html`Home Assistant not connected —
                <button class="link" @click=${() => this.requestEntityReload()}>${t("ui.settings.reloadEntities")}</button>`}
        </p>
        <p class="label">${t("ui.settings.readSensors")}</p>
        <div class="fields">
          ${INVERTER_READ_ENTITY_KEYS.map((k) =>
            k === "battery_power"
              ? this.renderBatteryPowerReadRow(read)
              : this.entityInput("inverter", "read", k, READ_DOMAIN[k] ?? "sensor"),
          )}
        </div>
        <p class="label">${t("ui.settings.writeEntities")}</p>
        <div class="fields">
          ${WRITE_ENTITY_KEYS.map((k) =>
            this.entityInput("inverter", "write", k, WRITE_DOMAIN[k] ?? "switch"),
          )}
        </div>
      `,
    );
  }

  private setGridChargeField(key: string, value: unknown): void {
    this.patchDraft((d) => {
      d.grid_charge = { ...(d.grid_charge ?? {}), [key]: value };
    });
  }

  private normalizeGridChargeForSave(draft: Record<string, unknown>): void {
    const gc = draft.grid_charge as Record<string, unknown> | undefined;
    if (!gc) return;
    delete gc.factor_order;
    const maxA = Number(gc.max_grid_charge_a ?? 60);
    const minA = Number(gc.min_grid_charge_a ?? 5);
    if (Number.isFinite(maxA) && Number.isFinite(minA)) {
      gc.max_grid_charge_a = Math.max(maxA, minA);
      gc.min_grid_charge_a = Math.min(minA, gc.max_grid_charge_a as number);
    }
  }

  private renderGridChargeSection() {
    const d = this.draft as unknown as Record<string, any>;
    const gc = d.grid_charge ?? {};
    const gcEnabled = gc.enabled !== false;
    return this.renderSectionPanel(
      sectionTitle("grid_charge"),
      sectionHelp("grid_charge"),
      html`
        <p class="label">${t("ui.settings.gridChargeIntro")}</p>
        ${!gcEnabled
          ? html`<p class="label" style="color:var(--muted)">${t("ui.settings.gridChargeDisabled")}</p>`
          : null}
        <div class="fields">
          <div class="field checkbox-row">
            <label>${this.lbl("grid_charge", "enabled")}</label>
            <input
              type="checkbox"
              .checked=${gcEnabled}
              @change=${(e: Event) =>
                this.setGridChargeField("enabled", (e.target as HTMLInputElement).checked)}
            />
          </div>
        </div>
        <details ?open=${gcEnabled}>
          <summary class="label">${t("ui.settings.gridChargeAdvanced")}</summary>
        <div class="fields">
          <div class="field">
            <label>${this.lbl("grid_charge", "ramp_enabled")}</label>
            <input
              type="checkbox"
              .checked=${Boolean(gc.ramp_enabled ?? true)}
              @change=${(e: Event) =>
                this.setGridChargeField("ramp_enabled", (e.target as HTMLInputElement).checked)}
            />
          </div>
          <div class="field">
            <label>${this.lbl("grid_charge", "max_grid_charge_a")}</label>
            <input
              type="number"
              step="any"
              .value=${String(gc.max_grid_charge_a ?? 60)}
              @input=${(e: Event) =>
                this.setGridChargeField(
                  "max_grid_charge_a",
                  Number((e.target as HTMLInputElement).value),
                )}
            />
          </div>
          <div class="field">
            <label>${this.lbl("grid_charge", "min_grid_charge_a")}</label>
            <input
              type="number"
              step="any"
              .value=${String(gc.min_grid_charge_a ?? 5)}
              @input=${(e: Event) =>
                this.setGridChargeField(
                  "min_grid_charge_a",
                  Number((e.target as HTMLInputElement).value),
                )}
            />
          </div>
          <div class="field">
            <label>${this.lbl("grid_charge", "ramp_step_a")}</label>
            <input
              type="number"
              step="any"
              .value=${String(gc.ramp_step_a ?? 10)}
              @input=${(e: Event) =>
                this.setGridChargeField("ramp_step_a", Number((e.target as HTMLInputElement).value))}
            />
          </div>
          <div class="field">
            <label>${this.lbl("grid_charge", "off_threshold_a")}</label>
            <input
              type="number"
              step="any"
              .value=${String(gc.off_threshold_a ?? 1)}
              @input=${(e: Event) =>
                this.setGridChargeField(
                  "off_threshold_a",
                  Number((e.target as HTMLInputElement).value),
                )}
            />
          </div>
          <div class="field">
            <label>${this.lbl("grid_charge", "next_solar_horizon_hours")}</label>
            <input
              type="number"
              step="1"
              .value=${String(gc.next_solar_horizon_hours ?? 6)}
              @input=${(e: Event) =>
                this.setGridChargeField(
                  "next_solar_horizon_hours",
                  Number((e.target as HTMLInputElement).value),
                )}
            />
          </div>
          <div class="field">
            <label>${this.lbl("grid_charge", "max_continuous_present_minutes")}</label>
            <input
              type="number"
              step="1"
              .value=${String(gc.max_continuous_present_minutes ?? 120)}
              @input=${(e: Event) =>
                this.setGridChargeField(
                  "max_continuous_present_minutes",
                  Number((e.target as HTMLInputElement).value),
                )}
            />
          </div>
          <div class="field">
            <label>${this.lbl("grid_charge", "grid_window_safety_factor")}</label>
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              .value=${String(gc.grid_window_safety_factor ?? 0.75)}
              @input=${(e: Event) =>
                this.setGridChargeField(
                  "grid_window_safety_factor",
                  Number((e.target as HTMLInputElement).value),
                )}
            />
          </div>
          <div class="field">
            <label>${this.lbl("grid_charge", "max_outage_ignore_minutes")}</label>
            <input
              type="number"
              step="1"
              .value=${String(gc.max_outage_ignore_minutes ?? 30)}
              @input=${(e: Event) =>
                this.setGridChargeField(
                  "max_outage_ignore_minutes",
                  Number((e.target as HTMLInputElement).value),
                )}
            />
          </div>
          <div class="field">
            <label>${this.lbl("grid_charge", "min_opportunity_present_minutes")}</label>
            <input
              type="number"
              step="1"
              .value=${String(gc.min_opportunity_present_minutes ?? 10)}
              @input=${(e: Event) =>
                this.setGridChargeField(
                  "min_opportunity_present_minutes",
                  Number((e.target as HTMLInputElement).value),
                )}
            />
          </div>
          <div class="field">
            <label>${this.lbl("grid_charge", "max_grid_import_w")}</label>
            <input
              type="number"
              step="any"
              .value=${gc.max_grid_import_w == null ? "" : String(gc.max_grid_import_w)}
              @input=${(e: Event) => {
                const raw = (e.target as HTMLInputElement).value.trim();
                this.setGridChargeField(
                  "max_grid_import_w",
                  raw === "" ? null : Number(raw),
                );
              }}
            />
          </div>
          <div class="field">
            <label>${this.lbl("grid_charge", "max_grid_import_entity")}</label>
            <solar-entity-input
              .entityId=${(gc.max_grid_import_entity ?? "") as string}
              .entities=${this.entities}
              .domains=${["number"]}
              placeholder="number.…"
              @entity-id-change=${(e: CustomEvent<string | null>) =>
                this.setGridChargeField("max_grid_import_entity", e.detail)}
            />
          </div>
        </div>
        </details>
      `,
    );
  }

  private renderConfigBackupSection() {
    return this.renderSectionPanel(
      t("ui.settings.configBackupTitle"),
      t("ui.settings.configBackupIntro"),
      html`
        <div class="buttons">
          <button type="button" @click=${() => void this.exportConfig()}>${t("ui.settings.exportConfig")}</button>
          <label style="padding:8px 14px;border-radius:8px;cursor:pointer;border:1px solid var(--border)">
            ${t("ui.settings.importConfig")}
            <input type="file" accept="application/json" hidden @change=${(e: Event) => this.importConfig(e)} />
          </label>
          <button type="button" @click=${() => void this.reset()}>${t("ui.settings.revertToFile")}</button>
        </div>
      `,
      "immediate",
    );
  }

  private renderModelSection() {
    return this.renderSectionPanel(
      t("ui.settings.trainedModelTitle"),
      t("ui.settings.trainedModelIntro"),
      html`
        <div class="buttons">
          <button type="button" @click=${() => void this.exportModel()}>${t("ui.settings.exportModel")}</button>
          <label style="padding:8px 14px;border-radius:8px;cursor:pointer;border:1px solid var(--border)">
            ${t("ui.settings.importModel")}
            <input type="file" accept="application/json" hidden @change=${(e: Event) => this.importModel(e)} />
          </label>
          <button type="button" @click=${() => void this.retrainModel()}>${t("ui.settings.retrainModel")}</button>
        </div>
      `,
      "immediate",
    );
  }

  private renderAdvancedSection() {
    return this.renderSectionPanel(
      t("ui.settings.advancedRawTitle"),
      t("ui.settings.advancedRawIntro"),
      html`
        <p class="label" style="color:var(--warn)">${t("ui.settings.advancedRawWarning")}</p>
        <textarea .value=${this.raw}
          @input=${(e: Event) => (this.raw = (e.target as HTMLTextAreaElement).value)}></textarea>
        <div class="buttons">
          <button type="button" @click=${() => void this.applyRaw()}>${t("ui.settings.applyRawJson")}</button>
        </div>
      `,
      "immediate",
    );
  }

  private renderSafetySection() {
    const d = this.draft as unknown as Record<string, any>;
    const fs = (d.fail_safe ?? {}) as Record<string, unknown>;
    const heartbeatEntity = (fs.heartbeat_entity ?? "") as string;
    return this.renderSectionPanel(
      t("ui.settings.nav.safety"),
      sectionHelp("fail_safe"),
      html`
        <p class="label">
          ${this.entitiesConnected
            ? t("ui.settings.inverterConnectedHint")
            : html`Home Assistant not connected —
                <button class="link" @click=${() => this.requestEntityReload()}>${t("ui.settings.reloadEntities")}</button>`}
        </p>
        <p class="label">${t("ui.settings.failSafeIntro")}</p>
        <div class="fields">
          ${typeof fs.heartbeat_enabled === "boolean"
            ? this.renderField("fail_safe", "heartbeat_enabled", fs.heartbeat_enabled)
            : null}
          <div class="field">
            <label>${this.lbl("fail_safe", "heartbeat_entity")}</label>
            <solar-entity-input
              .entityId=${heartbeatEntity}
              .entities=${this.entities}
              .domains=${["input_datetime"]}
              placeholder="input_datetime.solar_optimizer_heartbeat"
              @entity-id-change=${(e: CustomEvent<string | null>) =>
                this.setField("fail_safe", "heartbeat_entity", e.detail ?? "")}
            />
          </div>
          ${typeof fs.shutdown_failsafe_enabled === "boolean"
            ? this.renderField(
                "fail_safe",
                "shutdown_failsafe_enabled",
                fs.shutdown_failsafe_enabled,
              )
            : null}
        </div>
        ${this.renderLoadSheddingLink()}
      `,
    );
  }

  private renderValidationBanner() {
    if (!this.validationIssues.length) return null;
    return html`
      <div class="validation-banner" role="alert">
        <strong>${t("ui.settings.validation.fixBeforeSave")}</strong>
        <ul>
          ${this.validationIssues.map(
            (issue) => html`
              <li>
                ${t(issue.messageKey)}
                ${issue.navId
                  ? html`<button type="button" class="link" @click=${() => this.selectNav(issue.navId!)}>${t("ui.settings.checklist.goTo")}</button>`
                  : null}
              </li>
            `,
          )}
        </ul>
      </div>
    `;
  }

  private renderSetupChecklist() {
    if (this.checklistDismissed || !this.draft) return null;
    const mcpReady =
      this.mcpHealth != null
        ? Boolean(this.mcpHealth.mcp_enabled && this.mcpHealth.mcp_auth_configured)
        : undefined;
    const items = buildSetupChecklist(this.status, this.draft, this.entitiesConnected, mcpReady);
    if (!checklistNeedsAttention(items)) return null;
    const required = items.filter((i) => !i.optional);
    const done = required.filter((i) => i.done).length;
    const pct = required.length ? Math.round((done / required.length) * 100) : 100;
    return html`
      <div class="checklist-banner">
        <div class="checklist-header">
          <h4>${t("ui.settings.checklist.title")}</h4>
          <span class="label">${t("ui.settings.checklist.progress", { done: String(done), total: String(required.length) })}</span>
          <button type="button" class="link" @click=${() => (this.checklistDismissed = true)}>${t("ui.settings.checklist.dismiss")}</button>
        </div>
        <div class="checklist-progress" aria-hidden="true">
          <div class="checklist-progress-bar" style="width:${pct}%"></div>
        </div>
        ${items.map(
          (item) => html`
            <div class="checklist-row ${item.done ? "done" : ""}">
              <span class="checklist-icon">${item.done ? "✓" : item.optional ? "○" : "→"}</span>
              <span style="flex:1">${t(item.labelKey)}</span>
              ${!item.done
                ? html`<button type="button" class="link" @click=${() => this.selectNav(item.navId)}>${t("ui.settings.checklist.goTo")}</button>`
                : null}
            </div>
          `,
        )}
      </div>
    `;
  }

  private renderNavDesktop() {
    let lastCat: SettingsCategory | null = null;
    return html`
      <nav class="settings-nav settings-nav-desktop" aria-label=${t("ui.settings.title")}>
        ${SETTINGS_NAV.map((item) => {
          const showCat = item.category !== lastCat;
          lastCat = item.category;
          const label = this.navLabel(item.labelKey);
          if (this.searchQuery.trim() && !matchesSettingsSearch(this.searchQuery, label)) {
            return null;
          }
          return html`
            ${showCat
              ? html`<div class="nav-category-label">${t(`ui.settings.category.${item.category}`)}</div>`
              : null}
            <button
              type="button"
              class="nav-item ${this.activeNav === item.id ? "active" : ""}"
              aria-current=${this.activeNav === item.id ? "page" : nothing}
              @click=${() => this.selectNav(item.id)}
            >${label}</button>
          `;
        })}
      </nav>
    `;
  }

  private renderCategoryPills() {
    if (this.layoutWide || this.searchQuery.trim()) return null;
    return html`
      <div class="category-pills" role="tablist" aria-label=${t("ui.settings.categoryNav")}>
        ${SETTINGS_CATEGORIES.map(
          (cat) => html`
            <button
              type="button"
              role="tab"
              class="nav-pill ${this.mobileCategory === cat ? "active" : ""}"
              aria-selected=${this.mobileCategory === cat ? "true" : "false"}
              @click=${() => this.selectCategory(cat)}
            >${t(`ui.settings.category.${cat}`)}</button>
          `,
        )}
      </div>
    `;
  }

  private renderMobileSectionNav() {
    if (this.layoutWide || this.searchQuery.trim()) return null;
    const items = navItemsForCategory(this.mobileCategory);
    if (items.length <= 1) return null;
    return html`
      <nav class="settings-nav settings-mobile-section-nav" aria-label=${t("ui.settings.sectionNav")}>
        ${items.map(
          (item) => html`
            <button
              type="button"
              class="nav-item ${this.activeNav === item.id ? "active" : ""}"
              aria-selected=${this.activeNav === item.id ? "true" : "false"}
              aria-controls="settings-section-${item.id}"
              @click=${() => this.selectNav(item.id)}
            >${this.navLabel(item.labelKey)}</button>
          `,
        )}
      </nav>
    `;
  }

  private renderMobileNavStack() {
    if (this.layoutWide || this.searchQuery.trim()) return null;
    return html`
      <div class="settings-mobile-nav-stack">
        ${this.renderCategoryPills()}
        ${this.renderMobileSectionNav()}
      </div>
    `;
  }

  private renderNavSection(id: SettingsNavId): unknown {
    const content = this.renderNavPanel(id);
    if (content == null) return null;
    return html`
      <section id="settings-section-${id}" class="settings-nav-target" tabindex="-1">
        ${content}
      </section>
    `;
  }

  private renderNavPanel(id: SettingsNavId): unknown {
    switch (id) {
      case "setup_ha":
        return this.renderHaSection();
      case "setup_site":
        return this.renderSitePvSection();
      case "setup_inverter":
        return this.renderInverterMap();
      case "energy_battery":
        return this.renderSectionPanel(
          sectionTitle("battery"),
          sectionHelp("battery"),
          this.renderSectionFields("battery"),
        );
      case "energy_reserve":
        return this.renderSectionPanel(
          sectionTitle("reserve"),
          sectionHelp("reserve"),
          this.renderSectionFields("reserve"),
        );
      case "energy_grid":
        return this.renderGridChargeSection();
      case "engine":
        return this.renderEngineSection();
      case "forecast_temp":
        return this.renderTemperature();
      case "safety":
        return this.renderSafetySection();
      case "system_mcp":
        return this.renderMcpSection();
      case "system":
        return html`
          ${this.renderDisplayPreferencesSection()}
          ${this.renderSecuritySection()}
          ${this.session?.is_addon
            ? html`<p class="label">${t("ui.settings.haSupervisorNote")}</p>`
            : this.renderUpdatesSection()}
          ${this.renderConfigBackupSection()}
          ${this.renderModelSection()}
          ${this.renderAdvancedSection()}
        `;
      default:
        return null;
    }
  }

  private renderNavContent() {
    const q = this.searchQuery.trim();
    if (q) {
      const parts: unknown[] = [];
      for (const item of SETTINGS_NAV) {
        if (!matchesSettingsSearch(q, this.navLabel(item.labelKey))) continue;
        parts.push(this.renderNavSection(item.id));
      }
      return parts.length ? parts : html`<p class="label">${t("ui.settings.noSearchResults")}</p>`;
    }

    if (this.layoutWide) {
      return SETTINGS_NAV.map((item) => this.renderNavSection(item.id));
    }

    const parts: unknown[] = [];
    for (const item of navItemsForCategory(this.mobileCategory)) {
      parts.push(this.renderNavSection(item.id));
    }
    return parts;
  }

  private renderStickyBar() {
    const canRestart = Boolean(
      this.mcpSettings?.can_restart || this.updateInfo?.can_apply,
    );
    const showRestart = canRestart && !this.session?.is_addon;
    const restartHighlight = this.mcpPendingRestart && showRestart;
    return html`
      <div class="settings-sticky-bar">
        <div class="dirty-indicator">
          ${this.isDirty
            ? html`<span class="dirty-dot" aria-hidden="true"></span>${t("ui.settings.unsavedChanges")}`
            : html`<span class="label">${t("ui.settings.badge.server")}</span>`}
        </div>
        <div class="sticky-actions">
          ${showRestart
            ? html`<button
                type="button"
                class=${restartHighlight ? "restart-needed" : ""}
                ?disabled=${this.busy || this.restartBusy || this.updateBusy || this.updateWatchActive}
                @click=${() => void this.restartService()}
              >
                ${t("ui.settings.restartService")}
              </button>`
            : null}
          <button type="button" ?disabled=${!this.isDirty || this.busy} @click=${() => void this.reset()}>${t("ui.settings.revertToFile")}</button>
          <button type="button" ?disabled=${this.busy} @click=${() => void this.exportConfig()}>${t("ui.settings.exportConfig")}</button>
          <button class="primary" type="button" ?disabled=${!this.isDirty || this.busy} @click=${() => void this.save()}>${t("ui.settings.saveChanges")}</button>
        </div>
      </div>
    `;
  }

  render() {
    if (!this.draft) {
      return html`<div class="card"><h3>${t("ui.settings.title")}</h3><p class="label">${t("ui.settings.loading")}</p></div>`;
    }
    return html`
      <div class="card ${this.busy ? "busy" : ""}">
        <div class="settings-header">
          <h3 style="margin:0">${t("ui.settings.title")}</h3>
          <div class="settings-search">
            <input
              type="search"
              placeholder=${t("ui.settings.searchPlaceholder")}
              .value=${this.searchQuery}
              @input=${(e: Event) => (this.searchQuery = (e.target as HTMLInputElement).value)}
            />
          </div>
        </div>
        ${this.renderSetupChecklist()}
        ${this.renderValidationBanner()}
        ${this.renderMobileNavStack()}
        <div class="settings-shell">
          ${this.renderNavDesktop()}
          <div class="settings-content">${this.renderNavContent()}</div>
        </div>
        ${this.renderStickyBar()}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-settings-panel": SettingsPanel;
  }
}
