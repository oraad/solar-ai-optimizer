import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

import { formatRiskFromScore } from "../blackout-risk.js";
import { t } from "../i18n.js";
import { LocaleController } from "../locale-controller.js";
import { sharedStyles } from "../styles.js";
import type { SystemStatus } from "../types.js";

@customElement("solar-overview-hero")
export class OverviewHero extends LitElement {
  constructor() {
    super();
    new LocaleController(this);
  }

  static styles = [
    sharedStyles,
    css`
      .hero {
        display: flex;
        flex-wrap: wrap;
        gap: 16px 24px;
        align-items: center;
        justify-content: space-between;
        padding: 14px 18px;
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        box-shadow: var(--shadow);
      }
      .battery-block {
        display: flex;
        align-items: center;
        gap: 14px;
        flex: 1 1 240px;
        min-width: 0;
      }
      .soc-main {
        font-size: 1.75rem;
        font-weight: 700;
        font-variant-numeric: tabular-nums;
        line-height: 1;
      }
      .soc-bar-wrap { flex: 1; min-width: 120px; }
      .soc-bar {
        position: relative;
        height: 10px;
        border-radius: 6px;
        background: var(--track);
        overflow: hidden;
      }
      .soc-fill { height: 100%; background: linear-gradient(90deg, var(--good), var(--accent)); }
      .reserve-mark {
        position: absolute; top: -2px; width: 2px; height: 14px; background: var(--accent-2);
      }
      @media (max-width: 700px) {
        .hero { flex-direction: column; align-items: stretch; }
        .battery-block { flex-direction: column; align-items: stretch; }
      }
    `,
  ];

  @property({ attribute: false }) status: SystemStatus | null = null;

  render() {
    const telemetry = this.status?.telemetry ?? null;
    const d = this.status?.decision ?? null;
    const soc = telemetry?.battery_soc ?? null;
    const reserve = d?.reserve.target_soc ?? null;
    const riskScore = d?.blackout_risk_score ?? null;
    const risk = riskScore != null ? formatRiskFromScore(riskScore) : null;

    return html`
      <div class="hero">
        <div class="battery-block">
          <div class="soc-main">${soc != null ? `${soc.toFixed(0)}%` : "--"}</div>
          <div class="soc-bar-wrap">
            <div class="label">${t("ui.status.battery")}</div>
            <div class="soc-bar">
              <div class="soc-fill" style="width:${soc ?? 0}%"></div>
              ${reserve != null
                ? html`<div class="reserve-mark" style="left:${reserve}%"></div>`
                : null}
            </div>
            ${reserve != null
              ? html`<div class="label" style="margin-top:4px">${t("ui.status.hero.reserve", { soc: reserve.toFixed(0) })}</div>`
              : null}
          </div>
        </div>
        ${risk
          ? html`<span class="pill ${risk.pillClass}">${t("ui.status.hero.risk", { label: risk.label, pct: risk.pct ?? "" })}</span>`
          : null}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-overview-hero": OverviewHero;
  }
}
