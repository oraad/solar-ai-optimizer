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
import type { AppConfigView, CompanionEntity, EntityInfo } from "../types.js";

function tierSwitches(t: Record<string, unknown>): string[] {
  if (Array.isArray(t.switches)) {
    const list = t.switches.map((s) => String(s ?? ""));
    return list.length ? list : [""];
  }
  const legacy = String(t.switch ?? "").trim();
  return legacy ? [legacy] : [""];
}

function tierDeviceCount(t: Record<string, unknown>): number {
  return tierSwitches(t)
    .map((s) => s.trim())
    .filter(Boolean).length;
}

function stateEntitiesMap(t: Record<string, unknown>): Record<string, string[]> {
  const raw = t.state_entities;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const out: Record<string, string[]> = {};
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (Array.isArray(v)) out[k] = v.map(String);
  }
  return out;
}

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
        padding: 12px;
        padding-top: 40px;
      }
      .tier-summary {
        cursor: pointer;
        list-style: none;
      }
      .tier-summary::-webkit-details-marker {
        display: none;
      }
      .tier-block[open] > .tier-summary {
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
    `,
  ];

  @property({ attribute: false }) config: AppConfigView | null = null;
  @property({ attribute: false }) entities: EntityInfo[] = [];
  @property({ attribute: false }) entitiesConnected = false;

  @state() private draft: Record<string, unknown> | null = null;
  @state() private busy = false;
  @state() private companionMeta: Record<string, CompanionEntity[]> = {};

  connectedCallback(): void {
    super.connectedCallback();
    void this.loadConfig();
  }

  updated(changed: Map<string, unknown>): void {
    if (changed.has("config") && this.config && !this.draft) {
      this.draft = structuredClone(this.config.load_shedding ?? {}) as Record<string, unknown>;
    }
  }

  private async loadConfig(): Promise<void> {
    try {
      const cfg = await api.config();
      this.draft = structuredClone(cfg.load_shedding ?? {}) as Record<string, unknown>;
    } catch {
      /* non-fatal */
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
    const tiers = (this.draft?.tiers ?? []) as Record<string, unknown>[];
    for (let i = 0; i < tiers.length; i++) {
      const t = tiers[i];
      const name = String(t.name ?? "").trim();
      const entities = tierSwitches(t).map((s) => s.trim()).filter(Boolean);
      if (!name) return `Tier ${i + 1}: name is required.`;
      if (!entities.length) return `Tier "${name}": at least one shed entity is required.`;
    }
    return null;
  }

  private normalizeForSave(d: Record<string, unknown>): void {
    const tiers = (d.tiers ?? []) as Record<string, unknown>[];
    d.tiers = tiers.map((t) => {
      const switches = tierSwitches(t).map((s) => s.trim()).filter(Boolean);
      const { switch: _legacy, ...rest } = t as Record<string, unknown> & { switch?: string };
      return { ...rest, switches };
    });
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
    if (ok) await this.loadConfig();
    this.busy = false;
  }

  private async reset(): Promise<void> {
    if (!confirm(t("ui.loadShedding.revertConfirm"))) return;
    await this.loadConfig();
    this.companionMeta = {};
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

  render() {
    if (!this.draft) {
      return html`<div class="card"><h3>${t("ui.loadShedding.title")}</h3><p class="label">${t("common.loading")}</p></div>`;
    }
    const d = this.draft;
    const tiers = (d.tiers ?? []) as Record<string, unknown>[];
    return html`
      <div class="card ${this.busy ? "busy" : ""}">
        <h3>
          ${t("ui.loadShedding.title")}
          <solar-info-tip .text=${sectionHelp("load_shedding")!}></solar-info-tip>
        </h3>
        <p class="intro">${t("ui.loadShedding.intro")}</p>
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

        <p class="label" style="margin-top:16px">${t("ui.loadShedding.tiersIntro")}</p>
        <p class="label">
          ${this.entitiesConnected
            ? html`${t("ui.loadShedding.entitiesConnected")}`
            : html`${t("ui.loadShedding.entitiesDisconnected")}
                <button class="link" @click=${() => this.requestEntityReload()}>${t("ui.loadShedding.reloadEntities")}</button>
                ${t("ui.loadShedding.entitiesDisconnectedSuffix")}`}
        </p>
        ${tiers.map((tier, i) => {
          const se = stateEntitiesMap(tier);
          const tierName = String(tier.name ?? "").trim() || t("ui.loadShedding.tierDefault", { n: String(i + 1) });
          const deviceCount = tierDeviceCount(tier);
          const deviceLabel = deviceCount === 1 ? t("common.device") : t("common.devices");
          return html`
            <details class="tier-block">
              <summary class="tier-summary">
                <span class="tier-summary-text">
                  ${tierName}
                  <span class="tier-summary-meta">
                    · Shed ${tier.shed_below_soc ?? ""}% · Priority ${tier.priority ?? 0} ·
                    ${deviceCount} ${deviceLabel}
                  </span>
                </span>
              </summary>
              <button
                type="button"
                class="tier-dismiss danger icon-btn"
                aria-label=${t("ui.loadShedding.removeTier")}
                @click=${(e: Event) => {
                  e.preventDefault();
                  e.stopPropagation();
                  this.removeTier(i);
                }}
              >
                ×
              </button>
              <div class="fields">
                <div class="field">
                  <label>${this.lbl("name")}</label>
                  <input
                    type="text"
                    .value=${String(tier.name ?? "")}
                    @input=${(e: Event) =>
                      this.setTier(i, "name", (e.target as HTMLInputElement).value)}
                  />
                </div>
                <div class="field">
                  <label>${this.lbl("priority")}</label>
                  <input
                    type="number"
                    step="1"
                    .value=${String(tier.priority ?? 0)}
                    @input=${(e: Event) =>
                      this.setTier(i, "priority", Number((e.target as HTMLInputElement).value))}
                  />
                </div>
                <div class="field">
                  <label>${this.lbl("shed_below_soc")}</label>
                  <input
                    type="number"
                    step="any"
                    .value=${String(tier.shed_below_soc ?? "")}
                    @input=${(e: Event) =>
                      this.setTier(
                        i,
                        "shed_below_soc",
                        Number((e.target as HTMLInputElement).value),
                      )}
                  />
                </div>
                <div class="field">
                  <label>${this.lbl("restore_above_soc")}</label>
                  <input
                    type="number"
                    step="any"
                    .value=${String(tier.restore_above_soc ?? "")}
                    @input=${(e: Event) =>
                      this.setTier(
                        i,
                        "restore_above_soc",
                        Number((e.target as HTMLInputElement).value),
                      )}
                  />
                </div>
                <div class="field checkbox-row">
                  <label>${this.lbl("restore_enabled")}</label>
                  <input
                    type="checkbox"
                    .checked=${tier.restore_enabled !== false}
                    @change=${(e: Event) =>
                      this.setTier(i, "restore_enabled", (e.target as HTMLInputElement).checked)}
                  />
                </div>
                <div class="field checkbox-row">
                  <label>${this.lbl("restore_on_grid")}</label>
                  <input
                    type="checkbox"
                    .checked=${tier.restore_on_grid !== false}
                    @change=${(e: Event) =>
                      this.setTier(i, "restore_on_grid", (e.target as HTMLInputElement).checked)}
                  />
                </div>
              </div>
              <div class="shed-entities-header">
                <label class="label">${this.lbl("switches")}</label>
                <button
                  type="button"
                  class="icon-btn"
                  aria-label=${t("ui.loadShedding.addEntity")}
                  @click=${() => this.addTierEntity(i)}
                >
                  +
                </button>
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
                          @entity-id-change=${(e: CustomEvent<string | null>) =>
                            this.setTierSwitch(i, j, e.detail ?? "")}
                        />
                        <button
                          type="button"
                          class="danger icon-btn"
                          aria-label=${t("ui.loadShedding.removeEntity")}
                          ?disabled=${tierSwitches(tier).length <= 1}
                          @click=${() => this.removeTierEntity(i, j)}
                        >
                          <span aria-hidden="true">🗑</span>
                        </button>
                      </div>
                      ${entity.includes(".")
                        ? html`
                            <details class="companion-details">
                              <summary>${t("ui.loadShedding.companions", { count: String(companionIds.length) })}</summary>
                              ${companionIds.map((cid) => {
                                const c = this.companionDisplay(entity, cid);
                                return html`
                                  <div class="companion-row">
                                    <span class="domain-badge">${c?.domain ?? "?"}</span>
                                    <span>${c?.name ?? cid}</span>
                                    <button
                                      type="button"
                                      class="danger icon-btn"
                                      aria-label=${t("ui.loadShedding.removeCompanion")}
                                      @click=${() => this.removeCompanion(i, entity, cid)}
                                    >
                                      ×
                                    </button>
                                  </div>
                                `;
                              })}
                              <div class="row" style="margin-top:6px">
                                <button
                                  type="button"
                                  @click=${() => this.discoverCompanions(i, entity)}
                                >
                                  ${t("ui.loadShedding.rediscover")}
                                </button>
                                <button
                                  type="button"
                                  @click=${() => this.clearCompanions(i, entity)}
                                >
                                  ${t("ui.loadShedding.clearCompanions")}
                                </button>
                              </div>
                            </details>
                          `
                        : null}
                    </div>
                  `;
                },
              )}
            </details>
          `;
        })}
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
