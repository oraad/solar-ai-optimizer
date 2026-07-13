import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

import { formatRiskFromScore } from "../blackout-risk.js";
import { t } from "../i18n.js";
import { LocaleController } from "../locale-controller.js";
import { socFillStyle } from "../soc-bar.js";
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
      .soc-fill { height: 100%; }
      .reserve-mark {
        position: absolute; top: -2px; width: 2px; height: 14px; background: var(--accent-2);
      }
      @media (max-width: 700px) {
        .hero {
          flex-direction: column;
          align-items: stretch;
          justify-content: flex-start;
          gap: 12px;
        }
        .battery-block {
          flex-direction: column;
          align-items: stretch;
          flex: 0 0 auto;
        }
      }
    `,
  ];

  @property({ attribute: false }) status: SystemStatus | null = null;

  private batteryDirLabel(power: number | null): string {
    if (power == null) return "";
    if (power > 20) return " ↑";  // charging
    if (power < -20) return " ↓"; // discharging
    return "";
  }

  render() {
    const telemetry = this.status?.telemetry ?? null;
    const d = this.status?.decision ?? null;
    const engineOn = this.status?.engine_enabled !== false;
    const soc = telemetry?.battery_soc ?? null;
    const battPower = telemetry?.battery_power ?? null;
    const minSoc = this.status?.battery_summary?.min_soc_floor ?? 20;
    const maxSoc = this.status?.battery_summary?.max_soc_ceiling ?? 100;
    const reserve = engineOn ? (d?.reserve.target_soc ?? null) : null;
    const riskScore = engineOn ? (d?.blackout_risk_score ?? null) : null;
    const risk = riskScore != null ? formatRiskFromScore(riskScore) : null;
    const dirLabel = this.batteryDirLabel(battPower);
    const battAriaLabel = soc != null
      ? `${t("ui.status.battery")}: ${soc.toFixed(0)}%${dirLabel ? (battPower! > 0 ? ` ${t("common.charging")}` : ` ${t("common.discharging")}`) : ""}`
      : t("ui.status.battery");

    return html`
      <div class="hero">
        <div class="battery-block">
          <div class="soc-main" aria-label=${battAriaLabel}>${soc != null ? `${soc.toFixed(0)}%${dirLabel}` : "--"}</div>
          <div class="soc-bar-wrap">
            <div class="label">${t("ui.status.battery")}</div>
            <div class="soc-bar">
              <div class="soc-fill" style=${socFillStyle(soc, minSoc, maxSoc)}></div>
              ${reserve != null
                ? html`<div
                    class="reserve-mark"
                    style="left:${reserve}%"
                    role="img"
                    aria-label=${t("ui.status.reserveMarkTitle")}
                  ></div>`
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
