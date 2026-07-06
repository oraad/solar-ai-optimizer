import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { api } from "../api.js";
import { overrideHelp } from "../field-help.js";
import { t } from "../i18n.js";
import { labelWithTip } from "../label-tip.js";
import { LocaleController } from "../locale-controller.js";
import { sharedStyles } from "../styles.js";
import { runWithToast } from "../toast.js";
import "./info-tip.js";
import type { AppConfigView, SystemStatus } from "../types.js";

@customElement("solar-overrides-panel")
export class OverridesPanel extends LitElement {
  constructor() {
    super();
    new LocaleController(this);
  }

  static styles = [
    sharedStyles,
    css`
      .section-label {
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: var(--muted);
        margin: 14px 0 8px;
      }
      .section-label:first-of-type { margin-top: 0; }
      .ctrl {
        display: flex; justify-content: space-between; align-items: center;
        gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--border);
        flex-wrap: wrap;
      }
      .ctrl:last-of-type { border-bottom: none; }
      .ctrl > span:first-child {
        font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em;
        color: var(--muted);
        display: inline-flex;
        align-items: center;
        gap: 4px;
      }
      .ctrl-segments {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-left: auto;
        flex-wrap: wrap;
      }
      .seg {
        display: inline-flex; background: var(--panel-2);
        border: 1px solid var(--border); border-radius: var(--radius-sm);
        padding: 3px; gap: 3px;
      }
      .seg button {
        border: none; background: transparent; border-radius: 7px;
        padding: 6px 12px; color: var(--muted); box-shadow: none;
      }
      .seg button:hover { color: var(--text); background: var(--panel); }
      .seg button.active { color: var(--text); background: var(--panel); box-shadow: var(--shadow); }
      .seg button.active.good { color: var(--good); }
      .seg button.active.warn { color: var(--warn); }
      .primary-row { display: flex; gap: 8px; flex-wrap: wrap; }
      .primary-row button { flex: 1 1 120px; min-height: 42px; }
      .reserve-input { display: flex; gap: 8px; align-items: center; }
      .reserve-input input { width: 84px; }
      .danger-zone {
        margin-top: 16px;
        padding-top: 14px;
        border-top: 1px solid color-mix(in srgb, var(--bad) 35%, var(--border));
      }
      .danger-zone button { width: 100%; }
      details.advanced { margin-top: 8px; }
      details.advanced summary {
        cursor: pointer;
        font-size: 0.78rem;
        color: var(--muted);
        font-weight: 600;
        margin-bottom: 8px;
      }
      .banner {
        padding: 10px 12px; border-radius: var(--radius-sm); margin-bottom: 12px;
        font-size: 0.82rem; border: 1px solid var(--border);
      }
      .banner.warn { background: color-mix(in srgb, var(--warn) 12%, var(--panel-2)); color: var(--warn); }
      .viewer-note { font-size: 0.78rem; color: var(--muted); margin: -4px 0 12px; }
      .seg button:disabled { opacity: 0.45; cursor: not-allowed; }
      @media (max-width: 760px) {
        .seg button, .primary-row button { min-height: 44px; padding: 8px 14px; }
      }
    `,
  ];

  @property({ attribute: false }) status: SystemStatus | null = null;
  @property({ attribute: false }) config: AppConfigView | null = null;
  @property({ type: String }) role: "admin" | "viewer" = "admin";

  @state() private busy = false;
  @state() private reserveInput: number | null = null;

  private dispatchRefresh(): void {
    window.dispatchEvent(new Event("solar-plan-refresh"));
  }

  private async run(
    fn: () => Promise<unknown>,
    loading: string,
    success: string,
  ): Promise<void> {
    this.busy = true;
    const ok = await runWithToast(async () => { await fn(); }, { loading, success });
    if (ok) this.dispatchRefresh();
    this.busy = false;
  }

  private toggleShadow = () =>
    this.run(
      () => api.override({ shadow_mode: !(this.status?.shadow_mode ?? true) }),
      t("ui.overrides.toastModeLoading"),
      t("ui.overrides.toastModeSuccess"),
    );

  private togglePauseAll = () =>
    this.run(
      () => api.override({ pause_engine: true }),
      t("ui.overrides.toastEngineLoading"),
      t("ui.overrides.toastEnginePaused"),
    );

  private resumeAll = () =>
    this.run(
      () => api.override({ pause_engine: false }),
      t("ui.overrides.toastEngineLoading"),
      t("ui.overrides.toastEngineResumed"),
    );

  private togglePauseShedding = () =>
    this.run(
      () => api.override({ pause_shedding: !(this.status?.paused_shedding ?? false) }),
      t("ui.overrides.toastEngineLoading"),
      t("ui.overrides.toastSubsystemSuccess"),
    );

  private resumeGridCharge = () =>
    this.run(
      () => api.override({ pause_grid_charge: false }),
      t("ui.overrides.toastEngineLoading"),
      t("ui.overrides.toastSubsystemSuccess"),
    );

  private pauseGridCharge = () =>
    this.run(
      () => api.override({ pause_grid_charge: true }),
      t("ui.overrides.toastEngineLoading"),
      t("ui.overrides.toastSubsystemSuccess"),
    );

  private togglePauseOptimization = () =>
    this.run(
      () => api.override({ pause_optimization: !(this.status?.paused_optimization ?? false) }),
      t("ui.overrides.toastEngineLoading"),
      t("ui.overrides.toastSubsystemSuccess"),
    );

  private forceCharge = () =>
    this.run(
      () => api.override({ force_grid_charge: true, pause_grid_charge: true }),
      t("ui.overrides.toastGridLoading"),
      t("ui.overrides.toastGridForced"),
    );

  private releaseGridCharge = () =>
    this.run(
      () => api.override({ pause_grid_charge: false }),
      t("ui.overrides.toastGridLoading"),
      t("ui.overrides.toastGridReleased"),
    );

  private applyReserve = () => {
    if (this.reserveInput == null) return;
    const soc = this.reserveInput;
    return this.run(
      () => api.override({ reserve_soc: soc }),
      t("ui.overrides.toastReserveLoading"),
      t("ui.overrides.toastReserveSuccess", { soc: String(soc) }),
    );
  };

  private clearAll = () =>
    this.run(
      () => api.clearOverride(),
      t("ui.overrides.toastClearLoading"),
      t("ui.overrides.toastClearSuccess"),
    );

  private killSwitch = () => {
    if (!confirm(t("ui.overrides.killConfirm"))) return;
    return this.run(
      () => api.override({ kill_switch: true, confirm: true }),
      t("ui.overrides.toastKillLoading"),
      t("ui.overrides.toastKillSuccess"),
    );
  };

  private forceCycle = () =>
    this.run(
      () => api.forceCycle(),
      t("ui.overrides.toastCycleLoading"),
      t("ui.overrides.toastCycleSuccess"),
    );

  private renderSubsystemPauses(
    pausedShed: boolean,
    pausedGrid: boolean,
    pausedOpt: boolean,
    gridChargeEnabled: boolean,
    forcedGrid: boolean,
  ) {
    const gridRunning = !pausedGrid && !forcedGrid;
    const gridPaused = pausedGrid || forcedGrid;
    return html`
      <div class="ctrl">
        <span>${t("ui.overrides.pauseShedding")}</span>
        <span class="seg">
          <button
            class=${pausedShed ? "active warn" : ""}
            ?disabled=${this.busy}
            @click=${this.togglePauseShedding}
          >
            ${pausedShed ? t("ui.overrides.paused") : t("ui.overrides.running")}
          </button>
        </span>
      </div>
      ${gridChargeEnabled
        ? html`
            <div class="ctrl">
              <span>${labelWithTip(t("ui.overrides.pauseGridCharge"), overrideHelp("grid_charge"))}</span>
              <span class="ctrl-segments">
                <span class="seg">
                  <button
                    class=${forcedGrid ? "" : "active good"}
                    ?disabled=${this.busy || !forcedGrid}
                    @click=${this.releaseGridCharge}
                  >
                    ${t("common.auto")}
                  </button>
                  <button
                    class=${forcedGrid ? "active warn" : ""}
                    ?disabled=${this.busy}
                    @click=${this.forceCharge}
                  >
                    ${t("ui.overrides.forceOn")}
                  </button>
                </span>
                <span class="seg">
                  <button
                    class=${gridRunning ? "active good" : ""}
                    ?disabled=${this.busy}
                    @click=${this.resumeGridCharge}
                  >
                    ${t("ui.overrides.running")}
                  </button>
                  <button
                    class=${gridPaused ? "active warn" : ""}
                    ?disabled=${this.busy}
                    @click=${this.pauseGridCharge}
                  >
                    ${t("ui.overrides.paused")}
                  </button>
                </span>
              </span>
            </div>
          `
        : null}
      <div class="ctrl">
        <span>${t("ui.overrides.pauseOptimization")}</span>
        <span class="seg">
          <button
            class=${pausedOpt ? "active warn" : ""}
            ?disabled=${this.busy}
            @click=${this.togglePauseOptimization}
          >
            ${pausedOpt ? t("ui.overrides.paused") : t("ui.overrides.running")}
          </button>
        </span>
      </div>
    `;
  }

  render() {
    const shadow = this.status?.shadow_mode ?? true;
    const pausedAll = this.status?.paused ?? false;
    const pausedShed = this.status?.paused_shedding ?? false;
    const pausedGrid = this.status?.paused_grid_charge ?? false;
    const pausedOpt = this.status?.paused_optimization ?? false;
    const gridChargeEnabled = this.status?.grid_charge_enabled !== false;
    const forcedGrid = this.status?.force_grid_charge_override === true;
    const viewer = this.role === "viewer";
    const partialPause =
      !pausedAll && (pausedShed || pausedGrid || pausedOpt);
    const anyPaused = pausedShed || pausedGrid || pausedOpt;
    return html`
      <div class="card ${this.busy ? "busy" : ""}">
        <h3>${viewer ? t("ui.overrides.titleViewer") : t("ui.overrides.title")}</h3>
        ${viewer ? html`<p class="viewer-note">${t("ui.overrides.viewerNote")}</p>` : null}

        ${pausedAll ? html`<div class="banner warn">${t("ui.overrides.enginePaused")}</div>` : null}
        ${partialPause && pausedShed ? html`<div class="banner warn">${t("ui.overrides.shedPausedOnly")}</div>` : null}
        ${partialPause && pausedGrid && !forcedGrid ? html`<div class="banner warn">${t("ui.overrides.gridPausedOnly")}</div>` : null}
        ${partialPause && pausedOpt ? html`<div class="banner warn">${t("ui.overrides.optPausedOnly")}</div>` : null}
        ${this.status?.reserve_soc_override != null
          ? html`<div class="banner warn">${t("ui.overrides.reservePinned", { soc: String(this.status.reserve_soc_override) })}</div>`
          : null}
        ${forcedGrid
          ? html`<div class="banner warn">${t("ui.overrides.gridChargeForced")}</div>`
          : null}

        <div class="section-label">${t("ui.overrides.sectionPrimary")}</div>
        <div class="primary-row">
          ${!pausedAll
            ? html`<button ?disabled=${this.busy} @click=${this.togglePauseAll}>&#10073;&#10073; ${t("ui.overrides.pauseAll")}</button>`
            : null}
          ${anyPaused
            ? html`<button class="primary" ?disabled=${this.busy} @click=${this.resumeAll}>&#9654; ${t("ui.overrides.resumeAll")}</button>`
            : null}
          ${viewer
            ? null
            : html`<button ?disabled=${this.busy} @click=${this.forceCycle}>&#8635; ${t("ui.overrides.runCycle")}</button>`}
        </div>

        ${this.renderSubsystemPauses(pausedShed, pausedGrid, pausedOpt, gridChargeEnabled, forcedGrid)}

        ${viewer
          ? html`
              <div class="danger-zone">
                <div class="section-label">${t("ui.overrides.sectionDanger")}</div>
                <button class="danger" @click=${this.killSwitch}>&#9760; ${t("ui.overrides.killSwitch")}</button>
              </div>
            `
          : html`
              <div class="section-label">${t("ui.overrides.sectionOverrides")}</div>
              <div class="ctrl">
                <span>${labelWithTip(t("ui.overrides.pinReserve"), overrideHelp("pin_reserve"))}</span>
                <span class="reserve-input">
                  <input
                    type="number"
                    min="0"
                    max="100"
                    placeholder=${t("common.auto")}
                    @input=${(e: Event) => {
                      const v = (e.target as HTMLInputElement).value;
                      this.reserveInput = v === "" ? null : Number(v);
                    }}
                  />
                  <button @click=${this.applyReserve}>${t("ui.overrides.set")}</button>
                </span>
              </div>

              <details class="advanced">
                <summary>${t("ui.overrides.sectionAdvanced")}</summary>
                <div class="ctrl">
                  <span>${labelWithTip(t("ui.overrides.mode"), overrideHelp("mode"))}</span>
                  <span class="seg">
                    <button class=${shadow ? "active warn" : ""} @click=${() => shadow || this.toggleShadow()}>${t("ui.overrides.shadow")}</button>
                    <button class=${shadow ? "" : "active good"} @click=${() => shadow && this.toggleShadow()}>${t("ui.overrides.live")}</button>
                  </span>
                </div>
                <button style="width:100%;margin-top:8px" @click=${this.clearAll}>${t("ui.overrides.clearOverrides")}</button>
              </details>

              <div class="danger-zone">
                <div class="section-label">${t("ui.overrides.sectionDanger")}</div>
                <button class="danger" @click=${this.killSwitch}>&#9760; ${t("ui.overrides.killSwitch")}</button>
              </div>
            `}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-overrides-panel": OverridesPanel;
  }
}
