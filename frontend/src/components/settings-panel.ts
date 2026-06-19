import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { api, getApiToken, setApiToken } from "../api.js";
import { entityLabel, fieldLabel, INVERTER_READ_ENTITY_KEYS, pvLabel, sectionTitle } from "../field-labels.js";
import { entityHelp, fieldHelp, pvHelp, sectionHelp } from "../field-help.js";
import { labelWithTip } from "../label-tip.js";
import { sharedStyles } from "../styles.js";
import "./entity-input.js";
import "./info-tip.js";
import type { AppConfigView, EntityInfo, SessionInfo, SystemStatus } from "../types.js";

type Section = Record<string, unknown>;

// Sections rendered as simple scalar forms.
const FORM_SECTIONS = [
  "battery",
  "reserve",
  "forecast",
  "control",
  "load_shedding",
] as const;

// Sections persisted on save (includes custom-rendered sections).
const SAVE_SECTIONS = [...FORM_SECTIONS, "engine", "inverter", "ha", "fail_safe"] as const;

// Read-only helper fields returned by the API that must not be edited.
const HIDDEN_FIELDS = new Set(["has_token"]);

// Expected HA domain for each inverter capability, used to scope autocomplete.
const READ_DOMAIN: Record<string, string> = { grid_present: "binary_sensor" };
const WRITE_DOMAIN: Record<string, string> = {
  grid_charge_enable: "switch",
  max_grid_charge_current: "number",
  work_mode: "select",
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

function tierSwitches(t: Record<string, unknown>): string[] {
  if (Array.isArray(t.switches)) {
    const list = t.switches.map((s) => String(s ?? ""));
    return list.length ? list : [""];
  }
  const legacy = String(t.switch ?? "").trim();
  return legacy ? [legacy] : [""];
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
      }
      .field { display: flex; flex-direction: column; gap: 3px; }
      .field label { font-size: 0.75rem; color: var(--muted); }
      .field input, .field select { width: 100%; box-sizing: border-box; }
      textarea { width: 100%; box-sizing: border-box; min-height: 160px; font-family: ui-monospace, monospace; font-size: 0.8rem; background: var(--panel-2); color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 8px; }
      .buttons { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
      .msg { color: var(--muted); font-size: 0.78rem; margin-top: 8px; min-height: 1em; }
      .msg.err { color: var(--bad); }
      button.link { background: none; border: none; color: var(--accent, #6ad); padding: 0; cursor: pointer; text-decoration: underline; font: inherit; }
    `,
  ];

  @property({ attribute: false }) config: AppConfigView | null = null;
  @property({ attribute: false }) status: SystemStatus | null = null;
  @property({ attribute: false }) session: SessionInfo | null = null;

  @state() private draft: AppConfigView | null = null;
  @state() private raw = "";
  @state() private msg = "";
  @state() private err = false;
  @state() private busy = false;
  @state() private entities: EntityInfo[] = [];
  @state() private entitiesConnected = false;
  @state() private apiToken = "";
  @state() private mpcAvailable = false;
  @state() private mlAvailable = false;
  @state() private mlLoadEnabled = false;

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

  private validateTiers(): string | null {
    const d = this.draft as unknown as Record<string, any>;
    const tiers = (d.load_shedding?.tiers ?? []) as Record<string, unknown>[];
    for (let i = 0; i < tiers.length; i++) {
      const t = tiers[i];
      const name = String(t.name ?? "").trim();
      const entities = tierSwitches(t).map((s) => s.trim()).filter(Boolean);
      if (!name) return `Tier ${i + 1}: name is required.`;
      if (!entities.length) return `Tier "${name}": at least one shed entity is required.`;
      for (const entity of entities) {
        if (!entity.includes(".")) {
          return `Tier "${name}": entity must look like switch.foo`;
        }
      }
    }
    return null;
  }

  private normalizeTiersForSave(d: Record<string, any>): void {
    const tiers = (d.load_shedding?.tiers ?? []) as Record<string, unknown>[];
    d.load_shedding = {
      ...(d.load_shedding ?? {}),
      tiers: tiers.map((t) => {
        const switches = tierSwitches(t).map((s) => s.trim()).filter(Boolean);
        const { switch: _legacy, ...rest } = t as Record<string, unknown> & {
          switch?: string;
        };
        return { ...rest, switches };
      }),
    };
  }

  private async save(): Promise<void> {
    if (!this.draft) return;
    this.patchDraft((d) => this.normalizeTiersForSave(d));
    const tierErr = this.validateTiers();
    if (tierErr) {
      this.msg = tierErr;
      this.err = true;
      return;
    }
    await this.run(async () => {
      const patch: Record<string, unknown> = {};
      const draftRec = this.draft as unknown as Record<string, unknown>;
      for (const sec of SAVE_SECTIONS) {
        if (draftRec[sec] !== undefined) {
          patch[sec] = draftRec[sec];
        }
      }
      const res = await api.putConfig(patch);
      if (!res.ok) throw new Error(res.error || "validation failed");
    }, "Configuration saved and applied.");
  }

  private async applyRaw(): Promise<void> {
    await this.run(async () => {
      const parsed = JSON.parse(this.raw);
      const res = await api.putConfig(parsed);
      if (!res.ok) throw new Error(res.error || "validation failed");
    }, "Raw configuration applied.");
  }

  private async reset(): Promise<void> {
    if (!confirm("Discard all UI overrides and revert to base defaults?")) return;
    await this.run(async () => { await api.resetConfig(); }, "Reverted to base config.");
  }

  private async exportConfig(): Promise<void> {
    await this.run(async () => {
      const cfg = await api.config();
      const blob = new Blob([JSON.stringify(cfg, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "solar-config.json";
      a.click();
      URL.revokeObjectURL(a.href);
    }, "Configuration exported.");
  }

  private importConfig(e: Event): void {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () =>
      void this.run(async () => {
        const data = JSON.parse(String(reader.result));
        const res = await api.putConfig(data);
        if (!res.ok) throw new Error(res.error || "import failed");
      }, "Configuration imported and applied.");
    reader.readAsText(file);
  }

  private async exportModel(): Promise<void> {
    await this.run(async () => {
      const model = await api.exportModel();
      const blob = new Blob([JSON.stringify(model, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "solar-model.json";
      a.click();
      URL.revokeObjectURL(a.href);
    }, "Model exported.");
  }

  private importModel(e: Event): void {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () =>
      void this.run(async () => {
        const data = JSON.parse(String(reader.result));
        const res = await api.importModel(data);
        if (!res.ok) throw new Error("import failed");
      }, "Model imported; ML retrain paused until you click Retrain from telemetry.");
    reader.readAsText(file);
  }

  private async retrainModel(): Promise<void> {
    await this.run(async () => {
      const res = await api.retrainModel();
      if (!res.ok) throw new Error("retrain failed");
      if (!res.trained) {
        throw new Error("insufficient telemetry history or ML not enabled");
      }
    }, "ML model retrained from telemetry.");
  }

  private async run(fn: () => Promise<void>, ok: string): Promise<void> {
    this.busy = true; this.msg = "Working..."; this.err = false;
    try {
      await fn();
      this.msg = ok; this.err = false;
      // Refresh draft from server after a successful change.
      await this.loadConfig();
      // HA may have (re)connected after a credential change; refresh suggestions.
      void this.loadEntities();
    } catch (e) {
      this.msg = `Error: ${(e as Error).message}`; this.err = true;
    } finally {
      this.busy = false;
    }
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

  private hasShedEntities(): boolean {
    return this.entities.some(
      (e) => e.domain === "switch" || e.domain === "input_boolean",
    );
  }

  private renderDatalists() {
    const domainLists = DATALIST_DOMAINS.map((dom) => {
      const opts = this.entities.filter((e) => e.domain === dom);
      return html`<datalist id="dl-${dom}">
        ${opts.map((e) => html`<option value=${e.entity_id}>${e.name}</option>`)}
      </datalist>`;
    });
    const shed = this.entities.filter(
      (e) => e.domain === "switch" || e.domain === "input_boolean",
    );
    return html`
      ${domainLists}
      <datalist id="dl-shed">
        ${shed.map((e) => html`<option value=${e.entity_id}>${e.name}</option>`)}
      </datalist>
    `;
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

  private setTier(i: number, key: string, value: unknown): void {
    this.patchDraft((d) => {
      const tiers = (d.load_shedding?.tiers ?? []) as Record<string, unknown>[];
      tiers[i] = { ...tiers[i], [key]: value };
      d.load_shedding = { ...(d.load_shedding ?? {}), tiers };
    });
  }

  private setTierSwitch(tierIdx: number, entityIdx: number, value: string): void {
    this.patchDraft((d) => {
      const tiers = (d.load_shedding?.tiers ?? []) as Record<string, unknown>[];
      const switches = [...tierSwitches(tiers[tierIdx])];
      switches[entityIdx] = value;
      const { switch: _legacy, ...rest } = tiers[tierIdx] as Record<string, unknown> & {
        switch?: string;
      };
      tiers[tierIdx] = { ...rest, switches };
      d.load_shedding = { ...(d.load_shedding ?? {}), tiers };
    });
  }

  private addTierEntity(tierIdx: number): void {
    this.patchDraft((d) => {
      const tiers = (d.load_shedding?.tiers ?? []) as Record<string, unknown>[];
      const switches = [...tierSwitches(tiers[tierIdx]), ""];
      const { switch: _legacy, ...rest } = tiers[tierIdx] as Record<string, unknown> & {
        switch?: string;
      };
      tiers[tierIdx] = { ...rest, switches };
      d.load_shedding = { ...(d.load_shedding ?? {}), tiers };
    });
  }

  private removeTierEntity(tierIdx: number, entityIdx: number): void {
    this.patchDraft((d) => {
      const tiers = (d.load_shedding?.tiers ?? []) as Record<string, unknown>[];
      const switches = tierSwitches(tiers[tierIdx]);
      switches.splice(entityIdx, 1);
      if (!switches.length) switches.push("");
      const { switch: _legacy, ...rest } = tiers[tierIdx] as Record<string, unknown> & {
        switch?: string;
      };
      tiers[tierIdx] = { ...rest, switches };
      d.load_shedding = { ...(d.load_shedding ?? {}), tiers };
    });
  }

  private addTier(): void {
    this.patchDraft((d) => {
      const tiers = [...((d.load_shedding?.tiers ?? []) as unknown[])];
      tiers.push({
        name: "tier",
        switches: [""],
        shed_below_soc: 40,
        restore_above_soc: 55,
        priority: tiers.length,
      });
      d.load_shedding = { ...(d.load_shedding ?? {}), tiers };
    });
  }

  private removeTier(i: number): void {
    this.patchDraft((d) => {
      const tiers = [...((d.load_shedding?.tiers ?? []) as unknown[])];
      tiers.splice(i, 1);
      d.load_shedding = { ...(d.load_shedding ?? {}), tiers };
    });
  }

  private renderTiers() {
    const d = this.draft as unknown as Record<string, any>;
    const tiers = (d.load_shedding?.tiers ?? []) as Record<string, any>[];
    return html`
      <details>
        <summary>
          <span class="summary-label">
            Load-shedding tiers
            <solar-info-tip .text=${sectionHelp("load_shedding")!}></solar-info-tip>
          </span>
        </summary>
        <p class="label">
          Map each sheddable tier to one or more switches. All entities in a tier shed and
          restore together. Lowest priority sheds first.
        </p>
        ${tiers.map(
          (t, i) => html`
            <div class="fields" style="margin-bottom:8px">
              <div class="field">
                <label>${this.lbl("load_shedding", "name")}</label>
                <input type="text" .value=${String(t.name ?? "")}
                  @input=${(e: Event) => this.setTier(i, "name", (e.target as HTMLInputElement).value)} />
              </div>
              <div class="field" style="grid-column: 1 / -1">
                <label>${this.lbl("load_shedding", "switches")}</label>
                ${tierSwitches(t).map(
                  (entity, j) => html`
                    <div class="row" style="margin-bottom:6px">
                      <solar-entity-input
                        .entityId=${entity}
                        .entities=${this.entities}
                        .domains=${["switch", "input_boolean"]}
                        .listId=${this.hasShedEntities() ? "dl-shed" : ""}
                        placeholder="switch.… or input_boolean.…"
                        @entity-id-change=${(e: CustomEvent<string | null>) =>
                          this.setTierSwitch(i, j, e.detail ?? "")}
                      />
                      <button
                        type="button"
                        ?disabled=${tierSwitches(t).length <= 1}
                        @click=${() => this.removeTierEntity(i, j)}
                      >
                        Remove
                      </button>
                    </div>
                  `,
                )}
                <button type="button" @click=${() => this.addTierEntity(i)}>Add entity</button>
              </div>
              <div class="field">
                <label>${this.lbl("load_shedding", "shed_below_soc")}</label>
                <input type="number" step="any" .value=${String(t.shed_below_soc ?? "")}
                  @input=${(e: Event) => this.setTier(i, "shed_below_soc", Number((e.target as HTMLInputElement).value))} />
              </div>
              <div class="field">
                <label>${this.lbl("load_shedding", "restore_above_soc")}</label>
                <input type="number" step="any" .value=${String(t.restore_above_soc ?? "")}
                  @input=${(e: Event) => this.setTier(i, "restore_above_soc", Number((e.target as HTMLInputElement).value))} />
              </div>
              <div class="field">
                <label>${this.lbl("load_shedding", "priority")}</label>
                <input type="number" step="1" .value=${String(t.priority ?? 0)}
                  @input=${(e: Event) => this.setTier(i, "priority", Number((e.target as HTMLInputElement).value))} />
              </div>
              <div class="field" style="justify-content:flex-end">
                <button @click=${() => this.removeTier(i)}>Remove tier</button>
              </div>
            </div>
          `,
        )}
        <div class="buttons">
          <button @click=${() => this.addTier()}>Add tier</button>
        </div>
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
        ${FORM_SECTIONS.map((s) => this.renderSection(s))}
        ${this.renderSolcastNote()}
        ${this.renderPvArrays()}
        ${this.renderEngineSection()}
        ${this.renderTemperature()}
        ${this.renderInverterMap()}
        ${this.renderTiers()}
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

        <div class="msg ${this.err ? "err" : ""}">${this.msg}</div>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-settings-panel": SettingsPanel;
  }
}
