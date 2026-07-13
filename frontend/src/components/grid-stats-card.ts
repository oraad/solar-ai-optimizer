import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

import { formatDateTime } from "../date-format.js";
import { t } from "../i18n.js";
import { LocaleController } from "../locale-controller.js";
import { sharedStyles } from "../styles.js";
import type { GridStats } from "../types.js";

@customElement("solar-grid-stats")
export class GridStatsCard extends LitElement {
  constructor() {
    super();
    new LocaleController(this);
  }

  static styles = [
    sharedStyles,
    css`
      .now {
        display: flex; align-items: center; justify-content: space-between;
        gap: 10px; padding: 12px; margin-bottom: 12px;
        background: var(--panel-2); border: 1px solid var(--border);
        border-radius: var(--radius-sm);
      }
      .now .lbl { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
      .bars { display: flex; flex-direction: column; gap: 12px; margin-bottom: 12px; }
      .bar .top { display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 0.82rem; }
      .bar .top .v { font-weight: 700; font-variant-numeric: tabular-nums; }
      .track { height: 8px; border-radius: 999px; background: var(--panel-2); border: 1px solid var(--border); overflow: hidden; }
      .fill { height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--accent-2), var(--good)); transition: width 0.4s ease; }
      .stat { display: flex; justify-content: space-between; padding: 7px 0; border-bottom: 1px solid var(--border); }
      .stat:last-of-type { border-bottom: none; }
      .stat .v { font-weight: 600; }
      .stats-loading {
        color: var(--muted);
        font-size: 0.82rem;
        padding: 8px 0 4px;
        font-style: italic;
      }
      .stats-unavailable {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 10px;
        color: var(--muted);
        font-size: 0.82rem;
        padding: 8px 0 12px;
        font-style: italic;
      }
      .retry-btn {
        font-size: 0.78rem;
        padding: 3px 10px;
        min-height: 28px;
      }
      .note { color: var(--muted); font-size: 0.78rem; margin-top: 10px; }
    `,
  ];

  @property({ attribute: false }) stats: GridStats | null = null;
  @property({ attribute: false }) livePresent: boolean | null = null;
  @property({ type: Boolean }) allowRetry = false;

  private onDateFormat = () => this.requestUpdate();
  private onLocale = () => this.requestUpdate();

  connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("solar-date-format-change", this.onDateFormat);
    window.addEventListener("solar-site-timezone-change", this.onDateFormat);
    window.addEventListener("solar-locale-change", this.onLocale);
  }

  disconnectedCallback(): void {
    window.removeEventListener("solar-date-format-change", this.onDateFormat);
    window.removeEventListener("solar-site-timezone-change", this.onDateFormat);
    window.removeEventListener("solar-locale-change", this.onLocale);
    super.disconnectedCallback();
  }

  private currentlyPresent(): boolean | null {
    if (this.livePresent !== null && this.livePresent !== undefined) {
      return this.livePresent;
    }
    return this.stats?.currently_present ?? null;
  }

  private fmtLastSeen(): string {
    const ls = this.stats?.last_seen;
    if (!ls) return t("common.never");
    return formatDateTime(ls);
  }

  private bar(label: string, pct: number | null) {
    const v = pct ?? 0;
    const clamped = Math.max(0, Math.min(100, v));
    return html`
      <div class="bar">
        <div class="top"><span>${label}</span><span class="v">${pct == null ? "--" : v.toFixed(1)}%</span></div>
        <div class="track"><div class="fill" style="width:${clamped}%"></div></div>
      </div>
    `;
  }

  private dispatchRetry(): void {
    this.dispatchEvent(new CustomEvent("solar-grid-stats-retry", { bubbles: true, composed: true }));
  }

  render() {
    const s = this.stats;
    const present = this.currentlyPresent();
    const hasStats = s != null;
    return html`
      <div class="card">
        <h3>${t("ui.grid.title")}</h3>
        <div class="now">
          <span class="lbl">${t("ui.grid.currently")}</span>
          <span class="pill ${present ? "good" : present === false ? "muted" : ""}">
            <span class="dot ${present ? "on" : "off"}"></span>
            ${present === null ? t("common.unknown") : present ? t("common.present") : t("common.absent")}
          </span>
        </div>
        ${hasStats
          ? html`
              <div class="bars">
                ${this.bar(t("ui.grid.uptime24h"), s.uptime_pct_24h)}
                ${this.bar(t("ui.grid.uptime7d"), s.uptime_pct_7d)}
              </div>
              <div class="stat"><span>${t("ui.grid.avgWindow")}</span><span class="v">${t("ui.grid.minutes", { n: s.avg_window_minutes.toFixed(0) })}</span></div>
              <div class="stat"><span>${t("ui.grid.transitions24h")}</span><span class="v">${s.transitions_24h}</span></div>
              <div class="stat"><span>${t("ui.grid.lastSeen")}</span><span class="v">${this.fmtLastSeen()}</span></div>
            `
          : html`
              <div class="stats-unavailable">
                <span>${t("ui.grid.statsUnavailable")}</span>
                ${this.allowRetry
                  ? html`<button type="button" class="retry-btn" @click=${this.dispatchRetry}>${t("ui.grid.retryStats")}</button>`
                  : null}
              </div>
            `}
        <div class="note">${t("ui.grid.note")}</div>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-grid-stats": GridStatsCard;
  }
}
