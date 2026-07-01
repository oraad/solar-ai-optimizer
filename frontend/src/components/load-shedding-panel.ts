import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { repeat } from "lit/directives/repeat.js";

import { api } from "../api.js";
import { SHED_DOMAINS } from "../entity-datalists.js";
import { fieldLabel } from "../field-labels.js";
import { fieldHelp, sectionHelp } from "../field-help.js";
import { t } from "../i18n.js";
import { labelWithTip } from "../label-tip.js";
import { LocaleController } from "../locale-controller.js";
import { sharedStyles } from "../styles.js";
import { runWithToast, showToast } from "../toast.js";
import "./entity-input.js";
import "./info-tip.js";
import type { AppConfigView, CompanionEntity, EntityInfo, ShedResult, SystemStatus } from "../types.js";
import {
  normalizeTiersForSave,
  stateEntitiesMap,
  tierDeviceCount,
  tierSwitches,
  validateLoadSheddingTiers,
} from "../load-shedding-utils.js";
import { groupShedResultsByTier } from "../shed-display.js";

@customElement("solar-load-shedding-panel")
export class LoadSheddingPanel extends LitElement {
  constructor() {
    super();
    new LocaleController(this);
  }

  static styles = [
    sharedStyles,
    css`
      .fields { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 14px; margin-top: 10px; }
      @media (max-width: 700px) { .fields { grid-template-columns: 1fr; } }
      .field { display: flex; flex-direction: column; gap: 3px; }
      .field label { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 2px; font-size: 0.75rem; color: var(--muted); }
      .field input { width: 100%; box-sizing: border-box; }
      .tier-block {
        position: relative;
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 10px 48px 10px 12px;
        margin-bottom: 12px;
      }
      .tier-block[open] {
        padding: 12px 48px 12px 12px;
      }
      .tier-summary {
        cursor: pointer;
        list-style: none;
      }
      .tier-summary::-webkit-details-marker {
        display: none;
      }
      .tier-summary-text {
        display: block;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-size: 0.88rem;
        font-weight: 600;
        color: var(--text);
      }
      .tier-summary-meta {
        color: var(--muted);
        font-weight: 500;
      }
      .tier-dismiss {
        position: absolute;
        top: 8px;
        right: 8px;
        z-index: 1;
      }
      .icon-btn {
        width: 34px;
        height: 34px;
        padding: 0;
        display: grid;
        place-items: center;
        flex-shrink: 0;
        font-size: 1.1rem;
        line-height: 1;
      }
      .shed-entities-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-top: 10px;
      }
      .entity-row {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 6px;
      }
      .entity-row solar-entity-input {
        flex: 1;
        min-width: 0;
      }
      .companion-details {
        margin-top: 6px;
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 6px 10px;
      }
      .companion-details summary {
        cursor: pointer;
        font-size: 0.8rem;
        color: var(--muted);
        font-weight: 600;
      }
      .companion-row {
        display: flex;
        align-items: center;
        gap: 8px;
        margin: 4px 0;
        font-size: 0.82rem;
      }
      .companion-row .icon-btn {
        width: 28px;
        height: 28px;
        font-size: 1rem;
        margin-inline-start: auto;
      }
      .domain-badge {
        font-size: 0.7rem;
        padding: 2px 6px;
        border-radius: 4px;
        background: var(--panel-2);
        border: 1px solid var(--border);
        color: var(--muted);
      }
      .buttons { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
      .intro { font-size: 0.85rem; color: var(--muted); line-height: 1.45; margin-bottom: 12px; }
      .live-block {
        margin: 12px 0 16px;
        padding: 12px;
        border: 1px solid var(--border);
        border-radius: var(--radius-sm);
        background: var(--panel-2);
      }
      .live-row { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; font-size: 0.82rem; }
      .live-links { display: flex; gap: 10px; margin-top: 8px; flex-wrap: wrap; }
      .live-links button.link-btn {
        background: none; border: none; color: var(--accent); padding: 0; font-size: 0.82rem; font-weight: 600; cursor: pointer;
      }
      .tier-ladder { margin-top: 12px; }
      .tier-card {
        border: 1px solid var(--border);
        border-radius: 8px;
        margin-bottom: 10px;
        overflow: hidden;
      }
      .tier-head {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 10px 12px;
        border: none;
        width: 100%;
        text-align: start;
        font: inherit;
        color: inherit;
        background: var(--panel-2);
        cursor: pointer;
      }
      .tier-head .priority { font-size: 0.72rem; color: var(--muted); min-width: 72px; }
      .tier-head .name { font-weight: 600; flex: 1; min-width: 0; }
      .tier-head .meta { font-size: 0.78rem; color: var(--muted); }
      .tier-body { padding: 12px; border-top: 1px solid var(--border); }
      .soc-mini {
        position: relative;
        height: 8px;
        border-radius: 4px;
        background: var(--track);
        margin: 8px 0;
        overflow: hidden;
      }
      .soc-band {
        position: absolute;
        top: 0;
        height: 100%;
        background: color-mix(in srgb, var(--warn) 35%, transparent);
      }
      .soc-slider-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
      .wizard-banner {
        padding: 12px;
        border-radius: var(--radius-sm);
        border: 1px dashed var(--accent);
        background: color-mix(in srgb, var(--accent) 8%, var(--panel-2));
        margin-bottom: 12px;
        font-size: 0.85rem;
      }
      .preset-row { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
      .preset-row button { font-size: 0.78rem; padding: 4px 10px; }
      .viewer-note { font-size: 0.78rem; color: var(--muted); margin: -4px 0 12px; }
      .banner {
        padding: 10px 12px;
        border-radius: var(--radius-sm);
        margin-bottom: 12px;
        font-size: 0.82rem;
        border: 1px solid var(--border);
      }
      .banner.warn {
        background: color-mix(in srgb, var(--warn) 12%, var(--panel-2));
        color: var(--warn);
      }
      .summary-pills { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
      .entity-id { font-family: ui-monospace, monospace; font-size: 0.82rem; }
      .read-value { font-size: 0.88rem; }
    `,
  ];

  @property({ attribute: false }) config: AppConfigView | null = null;
  @property({ attribute: false }) entities: EntityInfo[] = [];
  @property({ attribute: false }) entitiesConnected = false;
  @property({ attribute: false }) status: SystemStatus | null = null;
  @property({ attribute: false }) shedResults: ShedResult[] = [];
  @property({ type: String }) role: "admin" | "viewer" = "admin";

  @state() private draft: Record<string, unknown> | null = null;
  @state() private busy = false;
  @state() private companionMeta: Record<string, CompanionEntity[]> = {};
  @state() private expandedTier: number | null = null;
  @state() private snapshots: Array<{ entity: string; was_on: boolean; companion_count: number; captured_at: string }> = [];
  @state() private advisoryReserve = false;
  private savedSnapshot = "";

  private get viewer(): boolean {
    return this.role === "viewer";
  }

  connectedCallback(): void {
    super.connectedCallback();
    if (!this.viewer) {
      void this.loadSnapshots();
    }
  }

  private async loadSnapshots(): Promise<void> {
    try {
      const res = await api.shedSnapshots();
      this.snapshots = res.snapshots ?? [];
    } catch {
      this.snapshots = [];
    }
  }

  private emitDirty(dirty: boolean): void {
    if (this.viewer) return;
    window.dispatchEvent(
      new CustomEvent("solar-load-shedding-dirty", { detail: dirty, bubbles: true }),
    );
  }

  private syncDirtyFlag(): void {
    if (this.viewer) return;
    const snap = JSON.stringify(this.draft ?? {});
    this.emitDirty(snap !== this.savedSnapshot);
  }

  private syncFromConfig(): void {
    if (this.viewer) return;
    if (!this.config) return;
    const snap = JSON.stringify(this.config.load_shedding ?? {});
    const dirty = this.draft != null && JSON.stringify(this.draft) !== this.savedSnapshot;
    if (!this.draft || !dirty) {
      this.draft = structuredClone(this.config.load_shedding ?? {}) as Record<string, unknown>;
      this.savedSnapshot = snap;
      this.emitDirty(false);
    }
    const eng = this.config.engine as Record<string, unknown> | undefined;
    const gc = this.config.grid_charge as Record<string, unknown> | undefined;
    this.advisoryReserve = eng?.enabled !== false && gc?.enabled === false;
  }

  updated(changed: Map<string, unknown>): void {
    if (this.viewer) return;
    if (changed.has("config")) {
      this.syncFromConfig();
    }
  }

  private requestEntityReload(): void {
    window.dispatchEvent(new Event("solar-reload-entities"));
  }

  private patch(mutator: (d: Record<string, unknown>) => void): void {
    if (!this.draft) return;
    const copy = structuredClone(this.draft);
    mutator(copy);
    this.draft = copy;
    this.syncDirtyFlag();
  }

  private lbl(key: string) {
    return labelWithTip(fieldLabel("load_shedding", key), fieldHelp("load_shedding", key));
  }

  private setGlobal(key: string, value: unknown): void {
    this.patch((d) => {
      d[key] = value;
    });
  }

  private validateTiers(): string | null {
    return validateLoadSheddingTiers(this.draft, t);
  }

  private normalizeForSave(d: Record<string, unknown>): void {
    normalizeTiersForSave(d);
  }

  private async save(): Promise<void> {
    if (!this.draft) return;
    this.patch((d) => this.normalizeForSave(d));
    const err = this.validateTiers();
    if (err) {
      showToast({ message: err, variant: "error" });
      return;
    }
    this.busy = true;
    const ok = await runWithToast(
      async () => {
        const res = await api.putConfig({ load_shedding: this.draft });
        if (!res.ok) throw new Error(res.error || "validation failed");
      },
      { loading: t("ui.loadShedding.toastSaveLoading"), success: t("ui.loadShedding.toastSaveSuccess") },
    );
    if (ok) {
      this.savedSnapshot = JSON.stringify(this.draft);
      this.emitDirty(false);
      void this.loadSnapshots();
      window.dispatchEvent(new Event("solar-plan-refresh"));
    }
    this.busy = false;
  }

  private async applyShedOnlyPreset(advisory: boolean): Promise<void> {
    this.patch((d) => {
      d.enabled = true;
    });
    this.advisoryReserve = advisory;
    this.busy = true;
    const ok = await runWithToast(
      async () => {
        const res = await api.putConfig({
          load_shedding: { ...this.draft, enabled: true },
          grid_charge: { enabled: false },
          engine: { enabled: advisory },
        });
        if (!res.ok) throw new Error(res.error || "validation failed");
      },
      { loading: t("ui.loadShedding.toastSaveLoading"), success: t("ui.loadShedding.toastPresetSuccess") },
    );
    if (ok) {
      this.savedSnapshot = JSON.stringify(this.draft);
      this.emitDirty(false);
      window.dispatchEvent(new Event("solar-plan-refresh"));
    }
    this.busy = false;
  }

  private deploymentProfileLabel(): string {
    const p = this.status?.deployment_profile ?? "full";
    if (p === "shed_primary") return t("ui.loadShedding.profileShedPrimary");
    if (p === "shed_advisory") return t("ui.loadShedding.profileShedAdvisory");
    if (p === "custom") return t("ui.loadShedding.profileCustom");
    return t("ui.loadShedding.profileFull");
  }

  private renderPresetCard(): ReturnType<typeof html> {
    const profile = this.status?.deployment_profile ?? "full";
    const isShedMode = profile === "shed_primary" || profile === "shed_advisory";
    return html`
      <div class="wizard-banner">
        <strong>${t("ui.loadShedding.presetTitle")}</strong>
        <p style="margin:6px 0 0">${t("ui.loadShedding.presetIntro")}</p>
        <div class="preset-row">
          <button type="button" ?disabled=${this.busy} @click=${() => void this.applyShedOnlyPreset(false)}>
            ${t("ui.loadShedding.presetApply")}
          </button>
          ${isShedMode
            ? html`<span class="pill">${this.deploymentProfileLabel()}</span>`
            : null}
        </div>
        ${isShedMode
          ? html`
              <div class="field checkbox-row" style="margin-top:10px">
                <label>${t("ui.loadShedding.advisoryReserve")}</label>
                <input
                  type="checkbox"
                  .checked=${this.advisoryReserve}
                  @change=${(e: Event) => {
                    this.advisoryReserve = (e.target as HTMLInputElement).checked;
                    void this.applyShedOnlyPreset(this.advisoryReserve);
                  }}
                />
              </div>
              <p class="label">${t("ui.loadShedding.presetRequirements")}</p>
            `
          : null}
      </div>
    `;
  }

  private reset(): void {
    if (!confirm(t("ui.loadShedding.revertConfirm"))) return;
    if (this.config) {
      this.draft = structuredClone(this.config.load_shedding ?? {}) as Record<string, unknown>;
      this.savedSnapshot = JSON.stringify(this.draft);
      this.emitDirty(false);
    }
    this.companionMeta = {};
    this.expandedTier = null;
  }

  private applySocPreset(tierIdx: number, shed: number, restore: number): void {
    this.setTier(tierIdx, "shed_below_soc", shed);
    this.setTier(tierIdx, "restore_above_soc", restore);
  }

  private tierSummaryMeta(tier: Record<string, unknown>): string {
    const deviceCount = tierDeviceCount(tier);
    return t("ui.loadShedding.tierMeta", {
      soc: String(tier.shed_below_soc ?? ""),
      priority: String(tier.priority ?? 0),
      count: String(deviceCount),
      devices: deviceCount === 1 ? t("common.device") : t("common.devices"),
    });
  }

  private renderSocMini(shed: number, restore: number): ReturnType<typeof html> {
    const lo = Math.max(0, Math.min(shed, 100));
    const hi = Math.max(lo, Math.min(restore, 100));
    return html`
      <div class="soc-mini" title="${t("ui.loadShedding.shedBelow")} ${lo}% → ${t("ui.loadShedding.restoreAbove")} ${hi}%">
        <div class="soc-band" style="left:${lo}%;width:${hi - lo}%"></div>
      </div>
    `;
  }

  private renderLiveStatus(): ReturnType<typeof html> {
    const actions = this.status?.decision?.shed_actions ?? [];
    const results = groupShedResultsByTier(this.shedResults);
    const hasLive = actions.length > 0 || results.length > 0 || this.snapshots.length > 0;
    const profilePill = this.status?.deployment_profile
      ? html`<span class="pill">${this.deploymentProfileLabel()}</span>`
      : null;
    if (!hasLive) {
      return html`<div class="live-block">
        <div class="live-row">${profilePill}</div>
        <div class="label">${t("ui.loadShedding.noLiveStatus")}</div>
      </div>`;
    }
    return html`
      <div class="live-block">
        <div class="label">${t("ui.loadShedding.liveStatus")}</div>
        <div class="live-row">
          ${profilePill}
          ${results.length
            ? results.map(
                (r) => html`<span class="pill ${r.desired_on ? "good" : "bad"}">${r.tier}: ${r.desired_on ? t("common.on") : t("ui.decision.shed")} (${r.entities.length})</span>`,
              )
            : actions.map(
                (a) => html`<span class="pill ${a.desired_on ? "good" : "bad"}">${a.tier}: ${a.desired_on ? t("common.on") : t("ui.decision.shed")}</span>`,
              )}
          ${this.snapshots.length
            ? html`<span class="label">${this.snapshots.length} ${t("ui.loadShedding.snapshots")}</span>`
            : null}
        </div>
        <div class="live-links">
          <button type="button" class="link-btn" @click=${() => this.navigate("overview")}>${t("ui.loadShedding.viewOverview")} →</button>
          <button type="button" class="link-btn" @click=${() => this.navigate("history")}>${t("ui.loadShedding.viewHistory")} →</button>
        </div>
      </div>
    `;
  }

  private navigate(tab: "overview" | "history"): void {
    if (tab === "history") {
      window.dispatchEvent(
        new CustomEvent("solar-navigate-tab", {
          detail: { tab: "history", history: { view: "activity", activity: "shed" } },
          bubbles: true,
          composed: true,
        }),
      );
      return;
    }
    window.dispatchEvent(
      new CustomEvent("solar-navigate-tab", { detail: tab, bubbles: true, composed: true }),
    );
  }

  private setTier(i: number, key: string, value: unknown): void {
    this.patch((d) => {
      const tiers = [...((d.tiers ?? []) as Record<string, unknown>[])];
      tiers[i] = { ...tiers[i], [key]: value };
      d.tiers = tiers;
    });
  }

  private setTierSwitch(tierIdx: number, entityIdx: number, value: string): void {
    this.patch((d) => {
      const tiers = [...((d.tiers ?? []) as Record<string, unknown>[])];
      const switches = [...tierSwitches(tiers[tierIdx])];
      switches[entityIdx] = value;
      const { switch: _legacy, ...rest } = tiers[tierIdx] as Record<string, unknown> & {
        switch?: string;
      };
      tiers[tierIdx] = { ...rest, switches };
      d.tiers = tiers;
    });
    if (value.includes(".")) void this.discoverCompanions(tierIdx, value);
  }

  private addTierEntity(tierIdx: number): void {
    this.patch((d) => {
      const tiers = [...((d.tiers ?? []) as Record<string, unknown>[])];
      const switches = [...tierSwitches(tiers[tierIdx]), ""];
      const { switch: _legacy, ...rest } = tiers[tierIdx] as Record<string, unknown> & {
        switch?: string;
      };
      tiers[tierIdx] = { ...rest, switches };
      d.tiers = tiers;
    });
  }

  private removeTierEntity(tierIdx: number, entityIdx: number): void {
    this.patch((d) => {
      const tiers = [...((d.tiers ?? []) as Record<string, unknown>[])];
      const switches = tierSwitches(tiers[tierIdx]);
      switches.splice(entityIdx, 1);
      if (!switches.length) switches.push("");
      const { switch: _legacy, ...rest } = tiers[tierIdx] as Record<string, unknown> & {
        switch?: string;
      };
      tiers[tierIdx] = { ...rest, switches };
      d.tiers = tiers;
    });
  }

  private addTier(): void {
    this.patch((d) => {
      const tiers = [...((d.tiers ?? []) as unknown[])];
      tiers.push({
        name: "tier",
        switches: [""],
        shed_below_soc: 40,
        restore_above_soc: 55,
        priority: tiers.length,
        restore_enabled: true,
        restore_on_grid: true,
        state_entities: {},
      });
      d.tiers = tiers;
    });
  }

  private removeTier(i: number): void {
    this.patch((d) => {
      const tiers = [...((d.tiers ?? []) as unknown[])];
      tiers.splice(i, 1);
      d.tiers = tiers;
    });
  }

  private async discoverCompanions(tierIdx: number, powerEntity: string): Promise<void> {
    if (!powerEntity.includes(".")) return;
    try {
      const res = await api.shedDeviceCompanions(powerEntity);
      this.companionMeta = { ...this.companionMeta, [powerEntity]: res.companions };
      this.patch((d) => {
        const tiers = [...((d.tiers ?? []) as Record<string, unknown>[])];
        const t = { ...tiers[tierIdx] };
        const map = { ...stateEntitiesMap(t) };
        map[powerEntity] = res.companions.map((c) => c.entity_id);
        t.state_entities = map;
        tiers[tierIdx] = t;
        d.tiers = tiers;
      });
      if (res.warning) {
        showToast({ message: res.warning, variant: "info" });
      }
    } catch (e) {
      showToast({
        message: e instanceof Error ? e.message : t("ui.loadShedding.discoveryFailed"),
        variant: "error",
      });
    }
  }

  private removeCompanion(tierIdx: number, powerEntity: string, companionId: string): void {
    this.patch((d) => {
      const tiers = [...((d.tiers ?? []) as Record<string, unknown>[])];
      const t = { ...tiers[tierIdx] };
      const map = { ...stateEntitiesMap(t) };
      map[powerEntity] = (map[powerEntity] ?? []).filter((id) => id !== companionId);
      t.state_entities = map;
      tiers[tierIdx] = t;
      d.tiers = tiers;
    });
  }

  private clearCompanions(tierIdx: number, powerEntity: string): void {
    this.patch((d) => {
      const tiers = [...((d.tiers ?? []) as Record<string, unknown>[])];
      const t = { ...tiers[tierIdx] };
      const map = { ...stateEntitiesMap(t) };
      map[powerEntity] = [];
      t.state_entities = map;
      tiers[tierIdx] = t;
      d.tiers = tiers;
    });
  }

  private companionDisplay(powerEntity: string, companionId: string): CompanionEntity | null {
    const meta = this.companionMeta[powerEntity]?.find((c) => c.entity_id === companionId);
    if (meta) return meta;
    const domain = companionId.split(".", 1)[0] ?? "";
    return { entity_id: companionId, domain, name: companionId };
  }

  private onOffLabel(enabled: boolean): string {
    return enabled ? t("common.on") : t("common.off");
  }

  private renderViewerPauseBanners(): ReturnType<typeof html> {
    const pausedAll = this.status?.paused ?? false;
    const pausedShed = this.status?.paused_shedding ?? false;
    const partialPause = !pausedAll && pausedShed;
    return html`
      ${pausedAll ? html`<div class="banner warn">${t("ui.overrides.enginePaused")}</div>` : null}
      ${partialPause ? html`<div class="banner warn">${t("ui.overrides.shedPausedOnly")}</div>` : null}
    `;
  }

  private renderViewerConfigSummary(d: Record<string, unknown>): ReturnType<typeof html> {
    const tiers = (d.tiers ?? []) as unknown[];
    const enabled = Boolean(d.enabled);
    const restoreAll = d.restore_all_when_grid_present !== false;
    return html`
      <div class="summary-pills">
        <span class="pill">${t("ui.loadShedding.settingsSummary", {
          count: String(tiers.length),
          state: enabled ? t("ui.loadShedding.settingsEnabled") : t("ui.loadShedding.settingsDisabled"),
        })}</span>
        <span class="pill">${fieldLabel("load_shedding", "restore_all_when_grid_present")}: ${this.onOffLabel(restoreAll)}</span>
      </div>
    `;
  }

  private renderViewerTierBody(
    tier: Record<string, unknown>,
    tierIdx: number,
  ): ReturnType<typeof html> {
    const se = stateEntitiesMap(tier);
    const shedSoc = Number(tier.shed_below_soc ?? 40);
    const restoreSoc = Number(tier.restore_above_soc ?? 55);
    const switches = tierSwitches(tier).filter((id) => id.includes("."));
    return html`
      <div class="tier-body">
        <div class="fields">
          <div class="field">
            <span class="label">${this.lbl("name")}</span>
            <span class="read-value">${String(tier.name ?? "").trim() || t("ui.loadShedding.tierDefault", { n: String(tierIdx + 1) })}</span>
          </div>
          <div class="field">
            <span class="label">${this.lbl("priority")}</span>
            <span class="read-value">${String(tier.priority ?? 0)}</span>
          </div>
          <div class="field">
            <span class="label">${this.lbl("shed_below_soc")}</span>
            <span class="read-value">${shedSoc}%</span>
          </div>
          <div class="field">
            <span class="label">${this.lbl("restore_above_soc")}</span>
            <span class="read-value">${restoreSoc}%</span>
          </div>
          <div class="field">
            <span class="label">${this.lbl("restore_enabled")}</span>
            <span class="read-value">${this.onOffLabel(tier.restore_enabled !== false)}</span>
          </div>
          <div class="field">
            <span class="label">${this.lbl("restore_on_grid")}</span>
            <span class="read-value">${this.onOffLabel(tier.restore_on_grid !== false)}</span>
          </div>
        </div>
        <div class="label" style="margin-top:10px">${this.lbl("switches")}</div>
        ${switches.length
          ? switches.map((entity) => {
              const companionIds = se[entity] ?? [];
              return html`
                <div style="margin:8px 0;padding:8px;border:1px dashed var(--border);border-radius:6px">
                  <div class="entity-id">${entity}</div>
                  ${companionIds.length
                    ? html`
                        <div class="label" style="margin-top:8px">${t("ui.loadShedding.companions", { count: String(companionIds.length) })}</div>
                        ${companionIds.map((cid) => {
                          const c = this.companionDisplay(entity, cid);
                          return html`
                            <div class="companion-row">
                              <span class="domain-badge">${c?.domain ?? "?"}</span>
                              <span>${c?.name ?? cid}</span>
                            </div>
                          `;
                        })}
                      `
                    : null}
                </div>
              `;
            })
          : html`<p class="label">${t("ui.history.dash")}</p>`}
      </div>
    `;
  }

  private renderViewerTierLadder(d: Record<string, unknown>): ReturnType<typeof html> {
    const tiers = (d.tiers ?? []) as Record<string, unknown>[];
    const sortedIndices = tiers
      .map((_, i) => i)
      .sort((a, b) => Number(tiers[a]?.priority ?? 0) - Number(tiers[b]?.priority ?? 0));
    return html`
      <p class="label" style="margin-top:16px">${t("ui.loadShedding.tierLadder")}</p>
      <p class="label">${t("ui.loadShedding.tiersIntro")}</p>
      <div class="tier-ladder">
        ${sortedIndices.map((i) => {
          const tier = tiers[i]!;
          const tierName = String(tier.name ?? "").trim() || t("ui.loadShedding.tierDefault", { n: String(i + 1) });
          const shedSoc = Number(tier.shed_below_soc ?? 40);
          const restoreSoc = Number(tier.restore_above_soc ?? 55);
          const open = this.expandedTier === i;
          return html`
            <div class="tier-card">
              <button
                type="button"
                class="tier-head"
                aria-expanded=${open}
                @click=${() => { this.expandedTier = open ? null : i; }}
              >
                <span class="priority">${t("ui.loadShedding.priorityLabel", { n: String(tier.priority ?? i) })}</span>
                <span class="name">${tierName}</span>
                <span class="meta">${this.tierSummaryMeta(tier)}</span>
              </button>
              ${this.renderSocMini(shedSoc, restoreSoc)}
              ${open ? this.renderViewerTierBody(tier, i) : null}
            </div>
          `;
        })}
      </div>
    `;
  }

  private renderViewer(): ReturnType<typeof html> {
    const ls = this.config?.load_shedding;
    if (!ls) {
      return html`<div class="card"><h3>${t("ui.loadShedding.title")}</h3><p class="label">${t("common.loading")}</p></div>`;
    }
    const d = ls as Record<string, unknown>;
    return html`
      <div class="card">
        <h3>
          ${t("ui.loadShedding.title")}
          <solar-info-tip .text=${sectionHelp("load_shedding")!}></solar-info-tip>
        </h3>
        <p class="viewer-note">${t("ui.loadShedding.viewerNote")}</p>
        ${this.renderViewerPauseBanners()}
        ${this.renderLiveStatus()}
        ${this.renderViewerConfigSummary(d)}
        ${this.renderViewerTierLadder(d)}
      </div>
    `;
  }

  render() {
    if (this.viewer) return this.renderViewer();
    if (!this.draft) {
      return html`<div class="card"><h3>${t("ui.loadShedding.title")}</h3><p class="label">${t("common.loading")}</p></div>`;
    }
    const d = this.draft;
    const tiers = (d.tiers ?? []) as Record<string, unknown>[];
    const sortedIndices = tiers
      .map((_, i) => i)
      .sort((a, b) => Number(tiers[a]?.priority ?? 0) - Number(tiers[b]?.priority ?? 0));
    const showWizard = Boolean(d.enabled) && tiers.length === 0;

    return html`
      <div class="card ${this.busy ? "busy" : ""}">
        <h3>
          ${t("ui.loadShedding.title")}
          <solar-info-tip .text=${sectionHelp("load_shedding")!}></solar-info-tip>
        </h3>
        <p class="intro">${t("ui.loadShedding.intro")}</p>
        ${this.renderPresetCard()}
        ${this.renderLiveStatus()}
        <div class="fields">
          <div class="field checkbox-row">
            <label>${this.lbl("enabled")}</label>
            <input
              type="checkbox"
              .checked=${Boolean(d.enabled)}
              @change=${(e: Event) =>
                this.setGlobal("enabled", (e.target as HTMLInputElement).checked)}
            />
          </div>
          <div class="field checkbox-row">
            <label>${this.lbl("restore_all_when_grid_present")}</label>
            <input
              type="checkbox"
              .checked=${d.restore_all_when_grid_present !== false}
              @change=${(e: Event) =>
                this.setGlobal(
                  "restore_all_when_grid_present",
                  (e.target as HTMLInputElement).checked,
                )}
            />
          </div>
        </div>

        ${showWizard
          ? html`<div class="wizard-banner">
              <strong>${t("ui.loadShedding.wizardTitle")}</strong>
              <p style="margin:6px 0 0">${t("ui.loadShedding.wizardStep1")}</p>
            </div>`
          : null}

        <p class="label" style="margin-top:16px">${t("ui.loadShedding.tierLadder")}</p>
        <p class="label">${t("ui.loadShedding.tiersIntro")}</p>
        <p class="label">
          ${this.entitiesConnected
            ? html`${t("ui.loadShedding.entitiesConnected")}`
            : html`${t("ui.loadShedding.entitiesDisconnected")}
                <button class="link" @click=${() => this.requestEntityReload()}>${t("ui.loadShedding.reloadEntities")}</button>
                ${t("ui.loadShedding.entitiesDisconnectedSuffix")}`}
        </p>
        <div class="tier-ladder">
        ${sortedIndices.map((i) => {
          const tier = tiers[i]!;
          const se = stateEntitiesMap(tier);
          const tierName = String(tier.name ?? "").trim() || t("ui.loadShedding.tierDefault", { n: String(i + 1) });
          const shedSoc = Number(tier.shed_below_soc ?? 40);
          const restoreSoc = Number(tier.restore_above_soc ?? 55);
          const open = this.expandedTier === i;
          return html`
            <div class="tier-card">
              <button
                type="button"
                class="tier-head"
                aria-expanded=${open}
                @click=${() => { this.expandedTier = open ? null : i; }}
              >
                <span class="priority">${t("ui.loadShedding.priorityLabel", { n: String(tier.priority ?? i) })}</span>
                <span class="name">${tierName}</span>
                <span class="meta">${this.tierSummaryMeta(tier)}</span>
              </button>
              ${this.renderSocMini(shedSoc, restoreSoc)}
              ${open
                ? html`
                    <div class="tier-body">
                      <div class="row" style="justify-content:flex-end;margin-bottom:8px">
                        <button type="button" class="danger" @click=${() => this.removeTier(i)}>${t("ui.loadShedding.removeTier")}</button>
                      </div>
                      <div class="fields">
                        <div class="field">
                          <label>${this.lbl("name")}</label>
                          <input type="text" .value=${String(tier.name ?? "")} @input=${(e: Event) => this.setTier(i, "name", (e.target as HTMLInputElement).value)} />
                        </div>
                        <div class="field">
                          <label>${this.lbl("priority")}</label>
                          <input type="number" step="1" .value=${String(tier.priority ?? 0)} @input=${(e: Event) => this.setTier(i, "priority", Number((e.target as HTMLInputElement).value))} />
                        </div>
                      </div>
                      <div class="soc-slider-row">
                        <div class="field">
                          <label>${this.lbl("shed_below_soc")}</label>
                          <input type="range" min="5" max="95" .value=${String(shedSoc)} @input=${(e: Event) => this.setTier(i, "shed_below_soc", Number((e.target as HTMLInputElement).value))} />
                          <span class="label">${shedSoc}%</span>
                        </div>
                        <div class="field">
                          <label>${this.lbl("restore_above_soc")}</label>
                          <input type="range" min="5" max="100" .value=${String(restoreSoc)} @input=${(e: Event) => this.setTier(i, "restore_above_soc", Number((e.target as HTMLInputElement).value))} />
                          <span class="label">${restoreSoc}%</span>
                        </div>
                      </div>
                      <div class="label">${t("ui.loadShedding.wizardPresets")}</div>
                      <div class="preset-row">
                        <button type="button" @click=${() => this.applySocPreset(i, 25, 40)}>${t("ui.loadShedding.presetConservative")}</button>
                        <button type="button" @click=${() => this.applySocPreset(i, 35, 50)}>${t("ui.loadShedding.presetBalanced")}</button>
                        <button type="button" @click=${() => this.applySocPreset(i, 45, 60)}>${t("ui.loadShedding.presetAggressive")}</button>
                      </div>
                      <div class="fields">
                        <div class="field checkbox-row">
                          <label>${this.lbl("restore_enabled")}</label>
                          <input type="checkbox" .checked=${tier.restore_enabled !== false} @change=${(e: Event) => this.setTier(i, "restore_enabled", (e.target as HTMLInputElement).checked)} />
                        </div>
                        <div class="field checkbox-row">
                          <label>${this.lbl("restore_on_grid")}</label>
                          <input type="checkbox" .checked=${tier.restore_on_grid !== false} @change=${(e: Event) => this.setTier(i, "restore_on_grid", (e.target as HTMLInputElement).checked)} />
                        </div>
                      </div>
                      <div class="shed-entities-header">
                        <label class="label">${this.lbl("switches")}</label>
                        <button type="button" class="icon-btn" aria-label=${t("ui.loadShedding.addEntity")} @click=${() => this.addTierEntity(i)}>+</button>
                      </div>
                      ${repeat(
                        tierSwitches(tier),
                        (_entity, j) => `${i}-${j}`,
                        (entity, j) => {
                          const companionIds = se[entity] ?? [];
                          return html`
                            <div style="margin:8px 0;padding:8px;border:1px dashed var(--border);border-radius:6px">
                              <div class="entity-row">
                                <solar-entity-input
                                  .entityId=${entity}
                                  .entities=${this.entities}
                                  .domains=${SHED_DOMAINS}
                                  placeholder=${t("ui.loadShedding.entityPlaceholder")}
                                  @entity-id-change=${(e: CustomEvent<string | null>) => this.setTierSwitch(i, j, e.detail ?? "")}
                                />
                                <button type="button" class="danger icon-btn" aria-label=${t("ui.loadShedding.removeEntity")} ?disabled=${tierSwitches(tier).length <= 1} @click=${() => this.removeTierEntity(i, j)}>
                                  <span aria-hidden="true">🗑</span>
                                </button>
                              </div>
                              ${entity.includes(".")
                                ? html`
                                    <details class="companion-details">
                                      <summary>${t("ui.loadShedding.companionsAdvanced", { count: String(companionIds.length) })}</summary>
                                      ${companionIds.map((cid) => {
                                        const c = this.companionDisplay(entity, cid);
                                        return html`
                                          <div class="companion-row">
                                            <span class="domain-badge">${c?.domain ?? "?"}</span>
                                            <span>${c?.name ?? cid}</span>
                                            <button type="button" class="danger icon-btn" aria-label=${t("ui.loadShedding.removeCompanion")} @click=${() => this.removeCompanion(i, entity, cid)}>×</button>
                                          </div>
                                        `;
                                      })}
                                      <div class="row" style="margin-top:6px">
                                        <button type="button" @click=${() => this.discoverCompanions(i, entity)}>${t("ui.loadShedding.rediscover")}</button>
                                        <button type="button" @click=${() => this.clearCompanions(i, entity)}>${t("ui.loadShedding.clearCompanions")}</button>
                                      </div>
                                    </details>
                                  `
                                : null}
                            </div>
                          `;
                        },
                      )}
                    </div>
                  `
                : null}
            </div>
          `;
        })}
        </div>
        <button type="button" @click=${() => this.addTier()}>${t("ui.loadShedding.addTier")}</button>

        <div class="buttons">
          <button class="primary" @click=${() => void this.save()}>${t("common.save")}</button>
          <button @click=${() => void this.reset()}>${t("ui.loadShedding.revert")}</button>
        </div>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-load-shedding-panel": LoadSheddingPanel;
  }
}
