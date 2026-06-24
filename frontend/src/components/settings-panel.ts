import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { api, getApiToken, setApiToken } from "../api.js";
import { entityLabel, fieldLabel, gridChargeFactorLabel, INVERTER_READ_ENTITY_KEYS, optimizationPriorityLabel, pvLabel, sectionTitle } from "../field-labels.js";
import { entityHelp, fieldHelp, priorityEffectHelp, priorityRankBlurb, pvHelp, sectionHelp } from "../field-help.js";
import { labelWithTip } from "../label-tip.js";
import { sharedStyles } from "../styles.js";
import { dismissToast, runWithToast, showToast, updateToast } from "../toast.js";
import "./entity-input.js";
import "./info-tip.js";
import type { AppConfigView, EntityInfo, SessionInfo, SystemStatus, UpdateInfo } from "../types.js";

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
        white-space: pre-wrap;
        word-break: break-word;
      }
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

  connectedCallback(): void {
    super.connectedCallback();
    this.apiToken = getApiToken();
    if (this.config) this.setDraft(this.config);
    void this.loadConfig();
    void this.loadEntities();
    void this.loadCapabilities();
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
  private hasEntitiesForDomain(domain: string): boolean {
    return this.entities.some((e) => e.domain === domain);
  }

  private renderDatalists() {
    const domainLists = DATALIST_DOMAINS.map((dom) => {
      const opts = this.entities.filter((e) => e.domain === dom);
      return html`<datalist id="dl-${dom}">
        ${opts.map((e) => html`<option value=${e.entity_id}>${e.name}</option>`)}
      </datalist>`;
    });
    return html`${domainLists}`;
  }

  private entityInput(section: string, group: string, key: string, domain: string) {
    const d = this.draft as unknown as Record<string, any>;
    const value = (d[section]?.[group]?.[key] ?? "") as string;
    const listId = this.hasEntitiesForDomain(domain) ? `dl-${domain}` : "";
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
          .listId=${this.hasEntitiesForDomain("sensor") ? "dl-sensor" : ""}
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
              .listId=${this.hasEntitiesForDomain("input_datetime") ? "dl-input_datetime" : ""}
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
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
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

  private async waitForHealth(timeoutMs = 120_000, toastId?: string): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    const start = Date.now();
    while (Date.now() < deadline) {
      if (toastId) {
        const elapsed = Math.floor((Date.now() - start) / 1000);
        updateToast(toastId, {
          message: `Waiting for service to restart… (${elapsed}s)`,
        });
      }
      await new Promise((r) => setTimeout(r, 3000));
      try {
        const h = await api.health();
        if (h.status === "ok") return true;
      } catch {
        /* service restarting */
      }
    }
    return false;
  }

  private async applyUpdate(): Promise<void> {
    if (!this.updateInfo?.can_apply || !this.updateInfo.update_available) return;
    if (
      !window.confirm(
        "Install the latest release now? The service will restart and this page may disconnect briefly.",
      )
    ) {
      return;
    }
    const toastId = "update-apply";
    this.updateBusy = true;
    let reloaded = false;
    showToast({
      id: toastId,
      message: "Starting update…",
      variant: "loading",
      persistent: true,
    });
    try {
      await api.applyUpdate();
      updateToast(toastId, { message: "Pulling image and restarting container…" });
      const ok = await this.waitForHealth(120_000, toastId);
      if (ok) {
        updateToast(toastId, { message: "Update complete. Reloading…", variant: "success" });
        reloaded = true;
        window.location.reload();
      } else {
        dismissToast(toastId);
        showToast({
          message:
            "Update started but the service did not respond in time. Check container logs on the host.",
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
      if (!reloaded) void this.refreshUpdateInfo();
    }
  }

  private renderUpdatesSection() {
    const info = this.updateInfo;
    const current = info?.current_version ?? this.session?.version ?? "—";
    const latest = info?.latest_version;
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
          ${latest ? html` · latest release <strong>v${latest}</strong>` : null}
          ${info?.published_at && info.update_available
            ? html` · published ${this.formatPublishedAt(info.published_at)}`
            : null}
        </p>
        ${upToDate
          ? html`<p class="label">You are on the latest release.</p>`
          : info?.update_available
            ? html`<p class="label">A newer release is available.</p>`
            : html`<p class="label">Could not check for updates right now.</p>`}
        ${info?.release_url
          ? html`<p class="label">
              <a href=${info.release_url} target="_blank" rel="noopener noreferrer">View on GitHub</a>
            </p>`
          : null}
        ${info?.release_notes
          ? html`<div class="release-notes">${info.release_notes}</div>`
          : null}
        ${info?.can_apply && info.update_available
          ? html`
              <div class="buttons">
                <button
                  class="primary"
                  ?disabled=${this.updateBusy || info.update_in_progress}
                  @click=${() => void this.applyUpdate()}
                >
                  ${this.updateBusy || info.update_in_progress ? "Updating…" : "Update now"}
                </button>
                <button type="button" ?disabled=${this.updateBusy} @click=${() => void this.refreshUpdateInfo()}>
                  ${this.updateChecking ? "Checking…" : "Check again"}
                </button>
              </div>
            `
          : html`
              ${info?.apply_instructions
                ? html`<pre class="upgrade-cmd">${info.apply_instructions}</pre>`
                : null}
              <div class="buttons">
                <button
                  type="button"
                  ?disabled=${this.updateChecking}
                  @click=${() => void this.refreshUpdateInfo()}
                >
                  ${this.updateChecking ? "Checking…" : "Check for updates"}
                </button>
              </div>
            `}
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
        ${this.renderUpdatesSection()}
        ${FORM_SECTIONS.map((s) => this.renderSection(s))}
        ${this.renderSolcastNote()}
        ${this.renderPvArrays()}
        ${this.renderEngineSection()}
        ${this.renderTemperature()}
        ${this.renderInverterMap()}
        ${this.renderGridChargeSection()}
        <div class="buttons">
          <button class="primary" @click=${() => void this.save()}>Save changes</button>
          <button @click=${() => void this.reset()}>Revert to file</button>
          <button @click=${() => void this.exportConfig()}>Export config</button>
          <label style="padding:8px 14px;border-radius:8px;cursor:pointer;border:1px solid var(--border)">
            Import config
            <input type="file" accept="application/json" hidden @change=${(e: Event) => this.importConfig(e)} />
          </label>
        </div>

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

      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-settings-panel": SettingsPanel;
  }
}
