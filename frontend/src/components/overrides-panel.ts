import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { api } from "../api.js";
import { overrideHelp } from "../field-help.js";
import { labelWithTip } from "../label-tip.js";
import { sharedStyles } from "../styles.js";
import { runWithToast } from "../toast.js";
import "./info-tip.js";
import type { AppConfigView, SystemStatus } from "../types.js";

@customElement("solar-overrides-panel")
export class OverridesPanel extends LitElement {
  static styles = [
    sharedStyles,
    css`
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
      .reserve-input { display: flex; gap: 8px; align-items: center; }
      .reserve-input input { width: 84px; }
      .buttons { display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap; }
      .buttons button { flex: 1 1 auto; }
      .action-with-tip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        flex: 1 1 140px;
      }
      .action-with-tip button { flex: 1; }
      .banner {
        padding: 10px 12px; border-radius: var(--radius-sm); margin-bottom: 12px;
        font-size: 0.82rem; border: 1px solid var(--border);
      }
      .banner.warn { background: color-mix(in srgb, var(--warn) 12%, var(--panel-2)); color: var(--warn); }
      .banner.danger { background: color-mix(in srgb, var(--bad) 12%, var(--panel-2)); color: var(--bad); }
      .viewer-note { font-size: 0.78rem; color: var(--muted); margin: -4px 0 12px; }
      .seg button:disabled { opacity: 0.45; cursor: not-allowed; }
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
    const ok = await runWithToast(
      async () => {
        await fn();
      },
      { loading, success },
    );
    if (ok) this.dispatchRefresh();
    this.busy = false;
  }

  private toggleShadow = () =>
    this.run(
      () => api.override({ shadow_mode: !(this.status?.shadow_mode ?? true) }),
      "Updating mode…",
      "Shadow mode toggled.",
    );

  private togglePause = () =>
    this.run(() => api.override({ pause_engine: true }), "Updating engine…", "Engine paused.");

  private resume = () =>
    this.run(() => api.override({ pause_engine: false }), "Updating engine…", "Engine resumed.");

  private forceCharge = () =>
    this.run(
      () => api.override({ force_grid_charge: true }),
      "Updating grid charge…",
      "Forcing grid charge.",
    );

  private stopForceCharge = () =>
    this.run(
      () => api.override({ force_grid_charge: false }),
      "Updating grid charge…",
      "Released grid charge override.",
    );

  private applyReserve = () => {
    if (this.reserveInput == null) return;
    return this.run(
      () => api.override({ reserve_soc: this.reserveInput }),
      "Pinning reserve…",
      `Reserve pinned at ${this.reserveInput}%.`,
    );
  };

  private clearAll = () =>
    this.run(() => api.clearOverride(), "Clearing overrides…", "Overrides cleared (auto mode).");

  private killSwitch = () => {
    if (!confirm("Engage KILL SWITCH? This enables grid charge at max current, pauses the engine, and restores shed tiers.")) return;
    return this.run(
      () => api.override({ kill_switch: true, confirm: true }),
      "Engaging kill switch…",
      "Kill switch engaged; grid charge at max current.",
    );
  };

  private forceCycle = () =>
    this.run(() => api.forceCycle(), "Running control cycle…", "Control cycle executed.");

  private refreshForecast = () =>
    this.run(() => api.refreshForecast(), "Refreshing forecast…", "Forecast refreshed.");

  render() {
    const shadow = this.status?.shadow_mode ?? true;
    const paused = this.status?.paused ?? false;
    const viewer = this.role === "viewer";
    return html`
      <div class="card ${this.busy ? "busy" : ""}">
        <h3>${viewer ? "Operator controls" : "Controls &amp; overrides"}</h3>
        ${viewer
          ? html`<p class="viewer-note">Reserve pin and grid-charge overrides require an admin.</p>`
          : null}

        ${paused
          ? html`<div class="banner warn">Engine paused — no inverter or shed writes until resumed.</div>`
          : null}
        ${this.status?.reserve_soc_override != null
          ? html`<div class="banner warn">Reserve pinned at ${this.status.reserve_soc_override}%.</div>`
          : null}
        ${this.status?.force_grid_charge_override === true
          ? html`<div class="banner warn">Grid charge forced on.</div>`
          : null}
        ${!viewer && this.status?.force_grid_charge_override === false
          ? html`<div class="banner warn">Grid charge override: auto.</div>`
          : null}

        <div class="ctrl">
          <span>${labelWithTip("Mode", overrideHelp("mode"))}</span>
          <span class="seg">
            <button class=${shadow ? "active warn" : ""} @click=${() => shadow || this.toggleShadow()}>Shadow</button>
            <button class=${shadow ? "" : "active good"} @click=${() => shadow && this.toggleShadow()}>Live</button>
          </span>
        </div>

        <div class="ctrl">
          <span>${labelWithTip("Engine", overrideHelp("engine"))}</span>
          <span class="seg">
            <button class=${paused ? "active warn" : ""} ?disabled=${paused || this.busy} @click=${this.togglePause}>&#10073;&#10073; Pause</button>
            <button class=${paused ? "active good" : ""} ?disabled=${!paused || this.busy} @click=${this.resume}>&#9654; Resume</button>
          </span>
        </div>

        ${viewer
          ? html`
              <div class="buttons">
                <span class="action-with-tip">
                  <button class="danger" @click=${this.killSwitch}>&#9760; Kill switch</button>
                  <solar-info-tip .text=${overrideHelp("kill_switch")!}></solar-info-tip>
                </span>
              </div>
            `
          : html`
              <div class="ctrl">
                <span>${labelWithTip("Grid charge", overrideHelp("grid_charge"))}</span>
                <span class="seg">
                  <button @click=${this.forceCharge}>&#9889; Force on</button>
                  <button @click=${this.stopForceCharge}>Auto</button>
                </span>
              </div>

              <div class="ctrl">
                <span>${labelWithTip("Pin reserve", overrideHelp("pin_reserve"))}</span>
                <span class="reserve-input">
                  <input
                    type="number"
                    min="0"
                    max="100"
                    placeholder="auto"
                    @input=${(e: Event) => {
                      const v = (e.target as HTMLInputElement).value;
                      this.reserveInput = v === "" ? null : Number(v);
                    }}
                  />
                  <button @click=${this.applyReserve}>Set</button>
                </span>
              </div>

              <div class="buttons">
                <span class="action-with-tip">
                  <button @click=${this.forceCycle}>&#8635; Run cycle now</button>
                  <solar-info-tip .text=${overrideHelp("run_cycle")!}></solar-info-tip>
                </span>
                <span class="action-with-tip">
                  <button @click=${this.refreshForecast}>&#9728; Refresh forecast</button>
                  <solar-info-tip .text=${overrideHelp("refresh_forecast")!}></solar-info-tip>
                </span>
                <span class="action-with-tip">
                  <button @click=${this.clearAll}>Clear overrides</button>
                  <solar-info-tip .text=${overrideHelp("clear_overrides")!}></solar-info-tip>
                </span>
                <span class="action-with-tip">
                  <button class="danger" @click=${this.killSwitch}>&#9760; Kill switch</button>
                  <solar-info-tip .text=${overrideHelp("kill_switch")!}></solar-info-tip>
                </span>
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
