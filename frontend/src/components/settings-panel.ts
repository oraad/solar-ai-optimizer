import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { api, getApiToken, setApiToken } from "../api.js";
import {
  entityDatalistId,
  hasEntitiesForDomains,
  renderEntityDatalists,
} from "../entity-datalists.js";
import { entityLabel, fieldLabel, gridChargeFactorLabel, INVERTER_READ_ENTITY_KEYS, optimizationPriorityLabel, pvLabel, sectionTitle } from "../field-labels.js";
import { entityHelp, fieldHelp, priorityEffectHelp, priorityRankBlurb, pvHelp, sectionHelp } from "../field-help.js";
import { labelWithTip } from "../label-tip.js";
import { formatDateTime, getDateFormat, setDateFormat, type DateDisplayFormat } from "../date-format.js";
import { sharedStyles } from "../styles.js";
import { dismissToast, runWithToast, showToast, updateToast } from "../toast.js";
import "./entity-input.js";
import "./info-tip.js";
import type { AppConfigView, EntityInfo, ReleaseSummary, SessionInfo, SystemStatus, UpdateInfo, UpdateProgress, UpdateStage } from "../types.js";
import { renderMarkdown } from "../markdown.js";

type Section = Record<string, unknown>;

// Sections rendered as simple scalar forms.
const FORM_SECTIONS = [
  "battery",
  "reserve",
  "forecast",
  "control",
] as const;

// Sections persisted on save (includes custom-rendered sections).
const SAVE_SECTIONS = [...FORM_SECTIONS, "engine", "inverter", "ha", "fail_safe", "grid_charge"] as const;

const DEFAULT_GRID_CHARGE_FACTORS = [
  "soc_gap",
  "grid_window",
  "battery_power",
  "remaining_solar_today",
  "next_solar_power",
  "load_power",
  "solar_bridge",
  "blackout_risk",
] as const;

const ALL_GRID_CHARGE_FACTORS = [...DEFAULT_GRID_CHARGE_FACTORS] as const;

const DEFAULT_PRIORITY_ORDER = [
  "resilience",
  "savings",
  "self_sufficiency",
] as const;

const SCHEMA_DOWNGRADE_NOTE =
  "If you saved config on a newer release, downgrading may ignore newer settings keys " +
  "(e.g. grid_charge.max_grid_charge_a on releases before schema v3).";

const UPDATE_STAGE_LABELS: Record<UpdateStage, string> = {
  starting: "Preparing update…",
  backing_up: "Backing up data…",
  pulling: "Pulling container image…",
  stopping: "Stopping current container…",
  restoring_data: "Restoring backup data…",
  recreating: "Starting updated container…",
  finishing: "Finalizing…",
  failed: "Update failed",
};

const UPDATE_FLOW_STAGES: UpdateStage[] = [
  "starting",
  "backing_up",
  "pulling",
  "stopping",
  "recreating",
  "finishing",
];

const RESTORE_FLOW_STAGES: UpdateStage[] = [
  "starting",
  "stopping",
  "restoring_data",
  "recreating",
  "finishing",
];

function stageLabel(stage: UpdateStage, progress?: UpdateProgress | null): string {
  if (progress?.message && progress.stage === stage) return progress.message;
  return UPDATE_STAGE_LABELS[stage] ?? stage;
}

function flowStages(operation: UpdateProgress["operation"]): UpdateStage[] {
  return operation === "restore" ? RESTORE_FLOW_STAGES : UPDATE_FLOW_STAGES;
}

function stageIndex(stages: UpdateStage[], stage: UpdateStage): number {
  const idx = stages.indexOf(stage);
  return idx >= 0 ? idx : 0;
}

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

const DATALIST_DOMAINS = [
  "sensor",
  "binary_sensor",
  "switch",
  "input_boolean",
  "number",
  "select",
  "input_datetime",
] as const;

function isScalar(v: unknown): v is number | string | boolean {
  return typeof v === "number" || typeof v === "string" || typeof v === "boolean";
}

@customElement("solar-settings-panel")
export class SettingsPanel extends LitElement {
  static styles = [
    sharedStyles,
    css`
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
      .release-notes :is(ul, ol) { margin: 0.35em 0; padding-left: 1.25em; }
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
        text-align: left;
        padding: 6px 8px;
        border-bottom: 1px solid var(--border);
        vertical-align: top;
      }
      .release-table th { color: var(--muted); font-weight: 600; }
      .release-badge {
        display: inline-block;
        margin-left: 6px;
        padding: 1px 6px;
        border-radius: 999px;
        font-size: 0.65rem;
        font-weight: 600;
        background: color-mix(in srgb, var(--muted) 18%, transparent);
        color: var(--muted);
      }
      .release-badge.current { color: var(--good, #6c6); background: color-mix(in srgb, var(--good, #6c6) 18%, transparent); }
      .release-badge.newer { color: var(--accent); background: color-mix(in srgb, var(--accent) 18%, transparent); }
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
        margin-left: 8px;
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
    `,
  ];

  @property({ attribute: false }) config: AppConfigView | null = null;
  @property({ attribute: false }) status: SystemStatus | null = null;
  @property({ attribute: false }) session: SessionInfo | null = null;
  @property({ attribute: false }) updateInfo: UpdateInfo | null = null;

  @state() private draft: AppConfigView | null = null;
  @state() private raw = "";
  @state() private busy = false;
  @state() private entities: EntityInfo[] = [];
  @state() private entitiesConnected = false;
  @state() private apiToken = "";
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

  private updateWatchToken = 0;
  private onDateFormatChange = () => {
    this.dateFormat = getDateFormat();
    this.requestUpdate();
  };

  connectedCallback(): void {
    super.connectedCallback();
    this.dateFormat = getDateFormat();
    window.addEventListener("solar-date-format-change", this.onDateFormatChange);
    this.apiToken = getApiToken();
    if (this.config) this.setDraft(this.config);
    void this.loadConfig();
    void this.loadEntities();
    void this.loadCapabilities();
    this.maybeResumeUpdateWatch();
  }

  disconnectedCallback(): void {
    window.removeEventListener("solar-date-format-change", this.onDateFormatChange);
    super.disconnectedCallback();
  }

  protected updated(changed: Map<PropertyKey, unknown>): void {
    if (changed.has("updateInfo")) {
      this.maybeResumeUpdateWatch();
    }
  }

  private maybeResumeUpdateWatch(): void {
    if (this.updateWatchActive || this.updateBusy) return;
    if (!this.updateInfo?.update_in_progress) return;
    void this.resumeUpdateWatch();
  }

  private async resumeUpdateWatch(): Promise<void> {
    this.updateWatchActive = true;
    this.updateBusy = true;
    const toastId = "update-resume";
    showToast({
      id: toastId,
      message: "Update in progress…",
      variant: "loading",
      persistent: true,
    });
    try {
      const result = await this.watchUpdateCompletion({ toastId });
      if (result.ok) {
        updateToast(toastId, { message: "Update complete. Reloading…", variant: "success" });
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
            "Update in progress but the service did not respond in time. Use Restore below if needed.",
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

  private async loadEntities(): Promise<void> {
    try {
      const res = await api.entities();
      this.entities = res.entities;
      this.entitiesConnected = res.connected;
    } catch {
      this.entities = [];
      this.entitiesConnected = false;
    }
  }

  private setDraft(cfg: AppConfigView): void {
    this.draft = structuredClone(cfg);
    this.raw = JSON.stringify(cfg, null, 2);
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
    this.patchDraft((d) => {
      this.normalizeGridChargeForSave(d);
      this.normalizePriorityOrderForSave(d);
    });
    await this.run(
      async () => {
        const patch: Record<string, unknown> = {};
        const draftRec = this.draft as unknown as Record<string, unknown>;
        for (const sec of SAVE_SECTIONS) {
          if (draftRec[sec] !== undefined) {
            patch[sec] = draftRec[sec];
          }
        }
        const res = await api.putConfig(patch);
        if (!res.ok) throw new Error(res.error || "validation failed");
      },
      "Saving configuration…",
      "Configuration saved and applied.",
    );
  }

  private async applyRaw(): Promise<void> {
    await this.run(
      async () => {
        const parsed = JSON.parse(this.raw);
        const res = await api.putConfig(parsed);
        if (!res.ok) throw new Error(res.error || "validation failed");
      },
      "Applying configuration…",
      "Raw configuration applied.",
    );
  }

  private async reset(): Promise<void> {
    if (!confirm("Discard all UI overrides and revert to base defaults?")) return;
    await this.run(
      async () => {
        await api.resetConfig();
      },
      "Reverting configuration…",
      "Reverted to base config.",
    );
  }

  private async exportConfig(): Promise<void> {
    await this.run(
      async () => {
        const cfg = await api.config();
        const blob = new Blob([JSON.stringify(cfg, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "solar-config.json";
        a.click();
        URL.revokeObjectURL(a.href);
      },
      "Exporting configuration…",
      "Configuration exported.",
    );
  }

  private importConfig(e: Event): void {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () =>
      void this.run(
        async () => {
          const data = JSON.parse(String(reader.result));
          const res = await api.putConfig(data);
          if (!res.ok) throw new Error(res.error || "import failed");
        },
        "Importing configuration…",
        "Configuration imported and applied.",
      );
    reader.readAsText(file);
  }

  private async exportModel(): Promise<void> {
    await this.run(
      async () => {
        const model = await api.exportModel();
        const blob = new Blob([JSON.stringify(model, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "solar-model.json";
        a.click();
        URL.revokeObjectURL(a.href);
      },
      "Exporting model…",
      "Model exported.",
    );
  }

  private importModel(e: Event): void {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () =>
      void this.run(
        async () => {
          const data = JSON.parse(String(reader.result));
          const res = await api.importModel(data);
          if (!res.ok) throw new Error("import failed");
        },
        "Importing model…",
        "Model imported; ML retrain paused until you click Retrain from telemetry.",
      );
    reader.readAsText(file);
  }

  private async retrainModel(): Promise<void> {
    await this.run(
      async () => {
        const res = await api.retrainModel();
        if (!res.ok) throw new Error("retrain failed");
        if (!res.trained) {
          throw new Error("insufficient telemetry history or ML not enabled");
        }
      },
      "Retraining model…",
      "ML model retrained from telemetry.",
    );
  }

  private async run(
    fn: () => Promise<void>,
    loading: string,
    success: string,
  ): Promise<void> {
    this.busy = true;
    const ok = await runWithToast(fn, { loading, success });
    if (ok) {
      await this.loadConfig();
      void this.loadEntities();
    }
    this.busy = false;
  }

  private lbl(section: string, key: string) {
    return labelWithTip(fieldLabel(section, key), fieldHelp(section, key));
  }

  private renderSection(name: string): unknown {
    const draftRec = this.draft as unknown as Record<string, Section> | null;
    const sec = draftRec?.[name];
    if (!sec) return null;
    const entries = Object.entries(sec).filter(
      ([k, v]) => isScalar(v) && !HIDDEN_FIELDS.has(k),
    );
    return html`
      <details>
        <summary>
          <span class="summary-label">
            ${sectionTitle(name)}
            ${sectionHelp(name)
              ? html`<solar-info-tip .text=${sectionHelp(name)!}></solar-info-tip>`
              : null}
          </span>
        </summary>
        <div class="fields">
          ${entries.map(([key, v]) => this.renderField(name, key, v as number | string | boolean))}
        </div>
      </details>
    `;
  }

  private renderField(section: string, key: string, value: number | string | boolean) {
    const label = this.lbl(section, key);
    if (section === "forecast" && key === "provider") {
      return html`<div class="field">
        <label>${label}</label>
        <select
          .value=${String(value)}
          @change=${(e: Event) =>
            this.setField(section, key, (e.target as HTMLSelectElement).value)}
        >
          <option value="open-meteo">Open-Meteo</option>
          <option value="solcast">Solcast</option>
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
  private renderDatalists() {
    return renderEntityDatalists(
      this.entities,
      DATALIST_DOMAINS.map((d) => ({ id: entityDatalistId(d), domains: [d] })),
    );
  }

  private entityInput(section: string, group: string, key: string, domain: string) {
    const d = this.draft as unknown as Record<string, any>;
    const value = (d[section]?.[group]?.[key] ?? "") as string;
    const listId = hasEntitiesForDomains(this.entities, [domain])
      ? entityDatalistId(domain)
      : "";
    return html`<div class="field">
      <label>${labelWithTip(entityLabel(key), entityHelp(key))}</label>
      <solar-entity-input
        .entityId=${value}
        .entities=${this.entities}
        .domains=${[domain]}
        .listId=${listId}
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
          .listId=${hasEntitiesForDomains(this.entities, ["sensor"]) ? entityDatalistId("sensor") : ""}
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
            "Invert battery power sign",
            "Enable if your inverter reports positive power when discharging. Does not change stored history.",
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

  private renderFailSafeSection() {
    const d = this.draft as unknown as Record<string, any>;
    const fs = (d.fail_safe ?? {}) as Record<string, unknown>;
    const heartbeatEntity = (fs.heartbeat_entity ?? "") as string;
    return html`
      <details>
        <summary>
          <span class="summary-label">
            ${sectionTitle("fail_safe")}
            <solar-info-tip .text=${sectionHelp("fail_safe")!}></solar-info-tip>
          </span>
        </summary>
        <p class="label">
          Import the HA fail-safe package to create
          <code>input_datetime.solar_optimizer_heartbeat</code>, or pick an existing
          helper. Max grid charge current comes from Battery → Max grid charge current (A).
        </p>
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
              .listId=${hasEntitiesForDomains(this.entities, ["input_datetime"])
                ? entityDatalistId("input_datetime")
                : ""}
              placeholder="input_datetime.solar_optimizer_heartbeat"
              @entity-id-change=${(e: CustomEvent<string | null>) =>
                this.setField("fail_safe", "heartbeat_entity", e.detail)}
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
      </details>
    `;
  }

  private renderHaSection() {
    const d = this.draft as unknown as Record<string, any>;
    const ha = (d.ha ?? {}) as Record<string, unknown>;
    const hasToken = Boolean(ha.has_token);
    return html`
      <details>
        <summary>
          <span class="summary-label">
            Home Assistant connection
            <solar-info-tip .text=${sectionHelp("ha")!}></solar-info-tip>
          </span>
        </summary>
        <div class="fields">
          ${this.renderField("ha", "base_url", String(ha.base_url ?? ""))}
          <div class="field">
            <label>${this.lbl("ha", "token")}</label>
            <input
              type="password"
              placeholder=${hasToken ? "(stored — enter new value to replace)" : "long-lived access token"}
              .value=${String(ha.token ?? "")}
              @input=${(e: Event) =>
                this.setField("ha", "token", (e.target as HTMLInputElement).value)}
            />
          </div>
          ${typeof ha.verify_ssl === "boolean"
            ? this.renderField("ha", "verify_ssl", ha.verify_ssl)
            : null}
        </div>
      </details>
    `;
  }

  private renderDisplayPreferencesSection() {
    return html`
      <details>
        <summary>Display preferences</summary>
        <p class="label">
          How dates and times appear in history tables, charts, and release lists on this browser.
        </p>
        <div class="fields">
          <div class="field">
            <label>Date format</label>
            <select
              .value=${this.dateFormat}
              @change=${(e: Event) => {
                const v = (e.target as HTMLSelectElement).value as DateDisplayFormat;
                this.dateFormat = v;
                setDateFormat(v);
              }}
            >
              <option value="locale">Locale (browser default)</option>
              <option value="ddmmyy">DD/MM/YY</option>
              <option value="iso">YYYY-MM-DD (ISO)</option>
            </select>
          </div>
        </div>
      </details>
    `;
  }

  private renderSecuritySection() {
    return html`
      <details>
        <summary>API security (standalone)</summary>
        ${this.session?.auth_mode === "local"
          ? html`
              <p class="label">
                Signed in as <strong>${this.session.display_name ?? this.session.username}</strong>.
              </p>
              <div class="buttons">
                <button
                  type="button"
                  @click=${async () => {
                    await api.logout();
                    window.dispatchEvent(new Event("solar-logout"));
                  }}
                >
                  Sign out
                </button>
              </div>
            `
          : null}
        <p class="label">
          When the backend has <code>API_TOKEN</code> set, paste the same value here
          so mutating requests (overrides, config save) are authorized.
        </p>
        <div class="fields">
          <div class="field" style="grid-column: 1 / -1">
            <label>${labelWithTip("API token", fieldHelp("security", "api_token"))}</label>
            <input
              type="password"
              placeholder="Bearer token (stored in this browser only)"
              .value=${this.apiToken}
              @input=${(e: Event) => {
                this.apiToken = (e.target as HTMLInputElement).value;
                setApiToken(this.apiToken.trim());
              }}
            />
          </div>
        </div>
      </details>
    `;
  }

  private formatPublishedAt(iso: string | null): string {
    if (!iso) return "";
    return formatDateTime(iso);
  }

  private async refreshUpdateInfo(): Promise<void> {
    const toastId = "update-check";
    this.updateChecking = true;
    showToast({
      id: toastId,
      message: "Checking for updates…",
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
        showToast({ message: "Could not check for updates right now.", variant: "error" });
      } else if (info.update_available) {
        showToast({
          message: `v${info.latest_version} is available — you're on v${info.current_version}.`,
          variant: "info",
        });
      } else {
        showToast({
          message: `You're on the latest release (v${info.latest_version}).`,
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
    this.updateInfo = info;
    if (info.update_progress) {
      this.updateProgress = info.update_progress;
    }
    this.dispatchEvent(
      new CustomEvent("solar-update-info", { detail: info, bubbles: true, composed: true }),
    );
  }

  private progressToastMessage(progress?: UpdateProgress | null, healthWait?: boolean): string {
    if (healthWait) return "Waiting for service to restart…";
    if (!progress) return "Update in progress…";
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
        if (sawInProgress || pollErrors > 0) break;
        await new Promise((r) => setTimeout(r, 2000));
      } catch {
        pollErrors += 1;
        if (sawInProgress || pollErrors >= 3) break;
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
    const confirmMsg = isDowngrade
      ? `Install v${target}? This is an older release.\n\n${downgradeWarning}${schemaNote}`
      : `Install v${target} now? The service will restart and this page may disconnect briefly.`;
    if (!window.confirm(confirmMsg)) return;

    const toastId = "update-apply";
    this.updateBusy = true;
    this.installRecoveryOffer = false;
    this.updateProgress = null;
    this.updateHealthWait = false;
    let reloaded = false;
    showToast({
      id: toastId,
      message: "Starting update…",
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
        updateToast(toastId, { message: "Update complete. Reloading…", variant: "success" });
        reloaded = true;
        window.location.reload();
      } else {
        this.installRecoveryOffer = true;
        dismissToast(toastId);
        showToast({
          message:
            "Update started but the service did not respond in time. Use Restore below to recover from the pre-install backup.",
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
      message: "Starting restore…",
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
        updateToast(toastId, { message: "Restore complete. Reloading…", variant: "success" });
        reloaded = true;
        window.location.reload();
      } else {
        dismissToast(toastId);
        showToast({
          message: "Restore started but the service did not respond in time. Check container logs on the host.",
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
    const inProgress = Boolean(this.updateInfo?.update_in_progress) || this.updateBusy;
    if (!inProgress && !progress) return null;

    const operation = progress?.operation ?? "update";
    const stages = flowStages(operation);
    const activeStage = this.updateHealthWait
      ? null
      : (progress?.stage ?? (this.updateInfo?.update_in_progress ? "starting" : null));
    const activeIdx = activeStage ? stageIndex(stages, activeStage) : stages.length;

    return html`
      <div class="update-progress">
        <h4>${this.updateHealthWait ? "Restarting service…" : "Update in progress"}</h4>
        ${stages.map((stage, idx) => {
          const done = idx < activeIdx;
          const active = !this.updateHealthWait && activeStage === stage;
          return html`
            <div class="update-step ${done ? "done" : ""} ${active ? "active" : ""}">
              <span class="update-step-icon">
                ${done ? "✓" : active ? html`<span class="update-spinner"></span>` : "·"}
              </span>
              <span>
                ${stageLabel(stage, active ? progress : null)}
                ${active && progress?.stage === "pulling" && progress.pull_detail
                  ? html`<span class="update-step-detail">${progress.pull_detail}</span>`
                  : null}
              </span>
            </div>
          `;
        })}
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
      failed?.message ??
      "The service did not respond after the last install attempt. Restore the pre-install backup to recover.";
    return html`
      <div class="recovery-banner">
        <p>${message}</p>
        ${backup
          ? html`
              <div class="buttons">
                <button
                  class="primary"
                  ?disabled=${this.updateBusy || Boolean(this.updateInfo?.update_in_progress)}
                  @click=${() => void this.restoreBackup(backup)}
                >
                  Restore last backup
                </button>
              </div>
            `
          : null}
      </div>
    `;
  }

  private renderReleaseRow(release: ReleaseSummary, info: UpdateInfo) {
    const minVer = info.min_self_update_version;
    const belowMin = this.versionBelowMin(release.version, minVer);
    const expanded = this.expandedRelease === release.version;
    const badge =
      release.relation === "current"
        ? html`<span class="release-badge current">current</span>`
        : release.relation === "newer"
          ? html`<span class="release-badge newer">newer</span>`
          : null;

    return html`
      <tr>
        <td>
          <strong>v${release.version}</strong>${badge}
          ${release.published_at
            ? html`<div class="label">${this.formatPublishedAt(release.published_at)}</div>`
            : null}
        </td>
        <td>
          ${release.release_notes
            ? html`
                <button type="button" class="link" @click=${() => this.toggleReleaseNotes(release.version)}>
                  ${expanded ? "Hide notes" : "Show notes"}
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
                  Install
                </button>
              `
            : release.relation === "current"
              ? html`<span class="label">Running</span>`
              : belowMin
                ? html`<span class="label">Below v${minVer}</span>`
                : info.deployment === "addon"
                  ? html`<span class="label">Use HA Supervisor</span>`
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

    return html`
      <details open>
        <summary>
          Software updates
          ${info?.update_available
            ? html`<span class="badge-update">v${latest} available</span>`
            : null}
        </summary>
        <p class="label">
          Running <strong>v${current}</strong>
          ${info?.previous_version
            ? html` · previously <strong>v${info.previous_version}</strong>`
            : null}
          ${latest ? html` · latest release <strong>v${latest}</strong>` : null}
        </p>
        ${upToDate
          ? html`<p class="label">You are on the latest release.</p>`
          : info?.update_available
            ? html`<p class="label">A newer release is available.</p>`
            : releases.length
              ? null
              : html`<p class="label">Could not check for updates right now.</p>`}
        ${info?.deployment === "addon"
          ? html`<p class="label">Install specific versions via Home Assistant Supervisor.</p>`
          : null}
        ${info?.deployment === "proxmox"
          ? html`<p class="label">On Proxmox you can also run <code>update</code> inside the LXC for host-side upgrades.</p>`
          : null}
        ${this.renderUpdateProgress()}
        ${this.renderRecoveryBanner()}
        ${releases.length
          ? html`
              <table class="release-table">
                <thead>
                  <tr>
                    <th>Version</th>
                    <th>Release notes</th>
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
                <summary>Data backups (${info.backups.length})</summary>
                <p class="label">Automatic backups created before each install.</p>
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
                        Restore
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
            ${this.updateChecking ? "Checking…" : "Check for updates"}
          </button>
        </div>
      </details>
    `;
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

  private renderSolcastNote() {
    const d = this.draft as unknown as Record<string, any>;
    const provider = String(d.forecast?.provider ?? "open-meteo");
    if (provider !== "solcast") return null;
    const configured = this.status?.solcast_configured ?? false;
    return html`
      <p class="label ${configured ? "" : "err"}">
        Solcast credentials (<code>SOLCAST_API_KEY</code>, <code>SOLCAST_RESOURCE_ID</code>)
        are set via environment or HA add-on options — not stored in this config file.
        ${configured ? "Credentials detected." : "Credentials missing or incomplete."}
      </p>
    `;
  }

  private renderPvArrays() {
    const d = this.draft as unknown as Record<string, any>;
    const arrays = (d.forecast?.arrays ?? []) as Record<string, any>[];
    return html`
      <details open>
        <summary>
          <span class="summary-label">
            PV arrays
            <solar-info-tip .text=${sectionHelp("pv_arrays")!}></solar-info-tip>
          </span>
        </summary>
        <p class="label">Each array is forecast separately (tilt/azimuth/kWp). Set site latitude/longitude above.</p>
        ${arrays.map(
          (a, i) => html`
            <div class="fields" style="margin-bottom:8px">
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
                <input type="number" step="any" .value=${String(a.azimuth ?? "")}
                  @input=${(e: Event) => this.setArray(i, "azimuth", Number((e.target as HTMLInputElement).value))} />
              </div>
              <div class="field" style="justify-content:flex-end">
                <button @click=${() => this.removeArray(i)}>Remove</button>
              </div>
            </div>
          `,
        )}
        <div class="buttons">
          <button @click=${() => this.addArray()}>Add array</button>
        </div>
      </details>
    `;
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
    return html`
      <details>
        <summary>
          <span class="summary-label">
            ${sectionTitle("engine")}
            <solar-info-tip .text=${sectionHelp("engine")!}></solar-info-tip>
          </span>
        </summary>
        <p class="label">
          Reorder to set which tradeoff wins when goals conflict. Savings means
          opportunistic grid use when present — not tariff or time-of-use
          optimization. Grid charge factor order (below) still applies; priorities
          scale how strongly each factor bucket influences the cap chain. When ramp
          is disabled, priorities affect reserve and risk only.
        </p>
        <div class="fields">
          <div class="field">
            <label>${this.lbl("engine", "mode")}</label>
            <select
              .value=${String(eng.mode ?? "rules")}
              @change=${(e: Event) =>
                this.setField("engine", "mode", (e.target as HTMLSelectElement).value)}
            >
              <option value="rules">Rules</option>
              <option value="mpc">MPC</option>
            </select>
          </div>
          ${typeof eng.mpc_horizon_hours === "number"
            ? this.renderField("engine", "mpc_horizon_hours", eng.mpc_horizon_hours)
            : null}
        </div>
        <p class="label" style="margin-top:12px">Optimization priority (highest first)</p>
        ${this.priorityOrder().map(
          (key, i) => html`
            <div class="row" style="margin-bottom:6px">
              <span style="flex:1">
                ${labelWithTip(
                  `${i + 1}. ${optimizationPriorityLabel(key)}`,
                  priorityEffectHelp(key),
                )}
              </span>
              <button type="button" ?disabled=${i === 0} @click=${() => this.movePriority(i, -1)}>
                ↑
              </button>
              <button
                type="button"
                ?disabled=${i === this.priorityOrder().length - 1}
                @click=${() => this.movePriority(i, 1)}
              >
                ↓
              </button>
            </div>
          `,
        )}
        <p class="label">
          ${this.priorityOrder()
            .map((key, i) => `${i + 1}. ${optimizationPriorityLabel(key)} — ${priorityRankBlurb(key)}`)
            .join(" ")}
        </p>
        ${eng.mode === "mpc" && !this.mpcAvailable
          ? html`<p class="label" style="color:var(--warn)">
              MPC is selected but PuLP is not installed in this image. Rebuild with
              <code>INSTALL_EXTRAS=1</code> (default) or install <code>pulp</code> locally.
              The app is running rules engine fallback.
            </p>`
          : null}
        ${this.mlLoadEnabled && !this.mlAvailable
          ? html`<p class="label" style="color:var(--warn)">
              ML load forecasting is enabled but scikit-learn is not available in this image.
            </p>`
          : null}
      </details>
    `;
  }

  private renderTemperature() {
    const d = this.draft as unknown as Record<string, any>;
    const t = (d.forecast?.temperature ?? {}) as Record<string, any>;
    const num = (key: string) => html`<div class="field">
      <label>${this.lbl("temperature", key)}</label>
      <input type="number" step="any" .value=${String(t[key] ?? "")}
        @input=${(e: Event) =>
          this.setNested("forecast", "temperature", key, Number((e.target as HTMLInputElement).value))} />
    </div>`;
    const bool = (key: string) => html`<div class="field checkbox-row">
      <label>${this.lbl("temperature", key)}</label>
      <input type="checkbox" .checked=${Boolean(t[key])}
        @change=${(e: Event) =>
          this.setNested("forecast", "temperature", key, (e.target as HTMLInputElement).checked)} />
    </div>`;
    return html`
      <details>
        <summary>
          <span class="summary-label">
            Temperature (heating/cooling)
            <solar-info-tip .text=${sectionHelp("temperature")!}></solar-info-tip>
          </span>
        </summary>
        <p class="label">
          Models heater/cooler load from outdoor temperature (Open-Meteo forecast +
          history). Optionally bias-corrected by a Home Assistant sensor.
        </p>
        <div class="fields">
          ${bool("enabled")}
          ${this.entityInput("forecast", "temperature", "ha_entity", "sensor")}
          ${num("hdd_base_c")}
          ${num("cdd_base_c")}
          ${bool("use_month_fallback")}
          ${num("min_load_fraction")}
          ${num("training_days")}
        </div>
      </details>
    `;
  }

  private renderInverterMap() {
    const d = this.draft as unknown as Record<string, any>;
    const read = (d.inverter?.read ?? {}) as Record<string, unknown>;
    return html`
      <details open>
        <summary>
          <span class="summary-label">
            Inverter entity map
            <solar-info-tip .text=${sectionHelp("inverter")!}></solar-info-tip>
          </span>
        </summary>
        <p class="label">
          ${this.entitiesConnected
            ? html`Start typing to pick from your Home Assistant entities.`
            : html`Home Assistant not connected — set the connection above and
                <button class="link" @click=${() => void this.loadEntities()}>reload entities</button>
                for autocomplete.`}
        </p>
        <p class="label">Read sensors</p>
        <div class="fields">
          ${INVERTER_READ_ENTITY_KEYS.map((k) =>
            k === "battery_power"
              ? this.renderBatteryPowerReadRow(read)
              : this.entityInput("inverter", "read", k, READ_DOMAIN[k] ?? "sensor"),
          )}
        </div>
        <p class="label">Write entities</p>
        <div class="fields">
          ${WRITE_ENTITY_KEYS.map((k) =>
            this.entityInput("inverter", "write", k, WRITE_DOMAIN[k] ?? "switch"),
          )}
        </div>
      </details>
    `;
  }

  private gridChargeFactors(): string[] {
    const d = this.draft as unknown as Record<string, any>;
    const raw = d.grid_charge?.factor_order;
    if (!Array.isArray(raw) || raw.length === 0) {
      return [...DEFAULT_GRID_CHARGE_FACTORS];
    }
    const seen = new Set<string>();
    const out: string[] = [];
    for (const item of raw) {
      const key = String(item);
      if (!ALL_GRID_CHARGE_FACTORS.includes(key as (typeof ALL_GRID_CHARGE_FACTORS)[number])) continue;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(key);
    }
    return out.length ? out : [...DEFAULT_GRID_CHARGE_FACTORS];
  }

  private setGridChargeField(key: string, value: unknown): void {
    this.patchDraft((d) => {
      d.grid_charge = { ...(d.grid_charge ?? {}), [key]: value };
    });
  }

  private moveGridChargeFactor(i: number, dir: -1 | 1): void {
    this.patchDraft((d) => {
      const raw = (d.grid_charge as Record<string, unknown> | undefined)?.factor_order;
      const list =
        Array.isArray(raw) && raw.length
          ? [...raw.map(String)]
          : [...DEFAULT_GRID_CHARGE_FACTORS];
      const j = i + dir;
      if (j < 0 || j >= list.length) return;
      [list[i], list[j]] = [list[j], list[i]];
      d.grid_charge = { ...(d.grid_charge ?? {}), factor_order: list };
    });
  }

  private normalizeGridChargeForSave(draft: Record<string, unknown>): void {
    const gc = draft.grid_charge as Record<string, unknown> | undefined;
    if (!gc) return;
    const seen = new Set<string>();
    const order: string[] = [];
    const raw = Array.isArray(gc.factor_order) ? gc.factor_order : [];
    for (const item of raw) {
      const key = String(item);
      if (!ALL_GRID_CHARGE_FACTORS.includes(key as (typeof ALL_GRID_CHARGE_FACTORS)[number])) continue;
      if (seen.has(key)) continue;
      seen.add(key);
      order.push(key);
    }
    gc.factor_order = order.length ? order : [...DEFAULT_GRID_CHARGE_FACTORS];
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
    const factors = this.gridChargeFactors();
    return html`
      <details>
        <summary>
          <span class="summary-label">
            ${sectionTitle("grid_charge")}
            <solar-info-tip .text=${sectionHelp("grid_charge")!}></solar-info-tip>
          </span>
        </summary>
        <p class="label">
          All listed factors apply each cycle; the engine takes the lowest ceiling.
          Reordering only changes how the rationale is logged. Ramp step limits how
          fast amps change each cycle.
        </p>
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
        </div>
        <p class="label" style="margin-top:12px">Factor order (log display only)</p>
        ${factors.map(
          (key, i) => html`
            <div class="row" style="margin-bottom:6px">
              <span style="flex:1">${labelWithTip(gridChargeFactorLabel(key), fieldHelp("grid_charge", key))}</span>
              <button type="button" ?disabled=${i === 0} @click=${() => this.moveGridChargeFactor(i, -1)}>↑</button>
              <button
                type="button"
                ?disabled=${i === factors.length - 1}
                @click=${() => this.moveGridChargeFactor(i, 1)}
              >
                ↓
              </button>
            </div>
          `,
        )}
      </details>
    `;
  }

  render() {
    if (!this.draft) {
      return html`<div class="card"><h3>Settings</h3><p class="label">Loading config...</p></div>`;
    }
    return html`
      <div class="card ${this.busy ? "busy" : ""}">
        <h3>Settings (config from UI)</h3>
        ${this.renderDatalists()}
        ${this.renderHaSection()}
        ${this.renderFailSafeSection()}
        ${this.renderSecuritySection()}
        ${this.renderDisplayPreferencesSection()}
        ${this.renderUpdatesSection()}
        ${FORM_SECTIONS.map((s) => this.renderSection(s))}
        ${this.renderSolcastNote()}
        ${this.renderPvArrays()}
        ${this.renderEngineSection()}
        ${this.renderTemperature()}
        ${this.renderInverterMap()}
        ${this.renderGridChargeSection()}

        <details>
          <summary>Advanced: raw config + entity map (JSON)</summary>
          <p class="label">Edit any section, including the inverter entity map, forecast arrays, and load-shedding tiers.</p>
          <textarea .value=${this.raw}
            @input=${(e: Event) => (this.raw = (e.target as HTMLTextAreaElement).value)}></textarea>
          <div class="buttons">
            <button @click=${() => void this.applyRaw()}>Apply raw JSON</button>
          </div>
        </details>

        <details>
          <summary>Trained model (import / export)</summary>
          <p class="label">The learned bias correction and load profile. Export to back up or move to another instance. Importing an ML model pauses automatic retraining until you click Retrain.</p>
          <div class="buttons">
            <button @click=${() => void this.exportModel()}>Export model</button>
            <label class="primary" style="padding:8px 14px;border-radius:8px;cursor:pointer;border:1px solid var(--border)">
              Import model
              <input type="file" accept="application/json" hidden @change=${(e: Event) => this.importModel(e)} />
            </label>
            <button @click=${() => void this.retrainModel()}>Retrain from telemetry</button>
          </div>
        </details>

        <div class="buttons settings-footer">
          <button class="primary" @click=${() => void this.save()}>Save changes</button>
          <button @click=${() => void this.reset()}>Revert to file</button>
          <button @click=${() => void this.exportConfig()}>Export config</button>
          <label style="padding:8px 14px;border-radius:8px;cursor:pointer;border:1px solid var(--border)">
            Import config
            <input type="file" accept="application/json" hidden @change=${(e: Event) => this.importConfig(e)} />
          </label>
        </div>

      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-settings-panel": SettingsPanel;
  }
}
