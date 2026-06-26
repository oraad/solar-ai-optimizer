import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

import { formatHourWindow } from "../date-format.js";
import { t } from "../i18n.js";
import { LocaleController } from "../locale-controller.js";
import { sharedStyles } from "../styles.js";
import type { ForecastBundle, GridStats, SystemStatus } from "../types.js";

function peakLoadWindow(f: ForecastBundle | null): string | null {
  if (!f?.load?.length) return null;
  const now = Date.now();
  const future = f.load.filter((p) => new Date(p.ts).getTime() >= now - 3600_000);
  if (!future.length) return null;
  let maxAvg = 0;
  let maxStart = future[0]!.ts;
  const windowH = 3;
  for (let i = 0; i < future.length; i++) {
    const start = new Date(future[i]!.ts).getTime();
    const end = start + windowH * 3600_000;
    const inWindow = future.filter((p) => {
      const t = new Date(p.ts).getTime();
      return t >= start && t < end;
    });
    if (!inWindow.length) continue;
    const avg = inWindow.reduce((s, p) => s + p.load_power_w, 0) / inWindow.length;
    if (avg > maxAvg) {
      maxAvg = avg;
      maxStart = future[i]!.ts;
    }
  }
  if (maxAvg <= 0) return null;
  return formatHourWindow(maxStart, windowH);
}

function excessSolarKwh(f: ForecastBundle | null): number | null {
  if (!f?.solar?.length || !f.load?.length) return null;
  const solarMap = new Map(f.solar.map((p) => [Math.floor(new Date(p.ts).getTime() / 3600_000), p.pv_power_w]));
  const loadMap = new Map(f.load.map((p) => [Math.floor(new Date(p.ts).getTime() / 3600_000), p.load_power_w]));
  const nowH = Math.floor(Date.now() / 3600_000);
  let excessWh = 0;
  for (const [h, pv] of solarMap) {
    if (h < nowH) continue;
    const load = loadMap.get(h) ?? 0;
    if (pv > load) excessWh += (pv - load);
  }
  return excessWh > 0 ? excessWh / 1000 : null;
}

function reserveRunwayHours(status: SystemStatus | null): number | null {
  const soc = status?.telemetry?.battery_soc;
  const load = status?.telemetry?.load_power;
  const reserve = status?.decision?.reserve.target_soc;
  const cap = status?.battery_summary?.capacity_kwh;
  if (soc == null || load == null || load <= 20 || reserve == null || !cap) return null;
  const usableSoc = Math.max(0, soc - reserve);
  if (usableSoc <= 0) return 0;
  const kwh = (usableSoc / 100) * cap;
  return kwh / (load / 1000);
}

@customElement("solar-forecast-insights")
export class ForecastInsights extends LitElement {
  constructor() {
    super();
    new LocaleController(this);
  }

  static styles = [
    sharedStyles,
    css`
      .insight {
        padding: 10px 0;
        border-bottom: 1px solid var(--border);
        font-size: 0.85rem;
        line-height: 1.45;
      }
      .insight:last-of-type { border-bottom: none; }
      .insight .v { font-weight: 600; color: var(--text); }
      .grid-compact {
        margin-top: 14px;
        padding-top: 14px;
        border-top: 1px solid var(--border);
        font-size: 0.82rem;
      }
      .grid-compact .row { justify-content: space-between; }
      button.link-btn {
        background: none;
        border: none;
        color: var(--accent);
        padding: 0;
        font-size: inherit;
        font-weight: 600;
        cursor: pointer;
      }
      button.link-btn:hover { text-decoration: underline; }
    `,
  ];

  @property({ attribute: false }) forecast: ForecastBundle | null = null;
  @property({ attribute: false }) status: SystemStatus | null = null;
  @property({ attribute: false }) gridStats: GridStats | null = null;
  @property({ attribute: false }) livePresent: boolean | null = null;

  private goOverview(): void {
    window.dispatchEvent(
      new CustomEvent("solar-navigate-tab", { detail: "overview", bubbles: true, composed: true }),
    );
  }

  render() {
    const excess = excessSolarKwh(this.forecast);
    const peak = peakLoadWindow(this.forecast);
    const runway = reserveRunwayHours(this.status);
    const present = this.livePresent ?? this.gridStats?.currently_present ?? null;
    const uptime = this.gridStats?.uptime_pct_24h;

    return html`
      <div class="card">
        <h3>${t("ui.forecast.insightsTitle")}</h3>
        <div class="insight">
          <div class="label">${t("ui.forecast.excessSolar")}</div>
          <div class="v">${excess != null ? `~${excess.toFixed(1)} kWh` : t("ui.history.dash")}</div>
        </div>
        <div class="insight">
          <div class="label">${t("ui.forecast.peakLoad")}</div>
          <div class="v">${peak ?? t("ui.history.dash")}</div>
        </div>
        <div class="insight">
          <div class="label">${t("ui.forecast.reserveRunway")}</div>
          <div class="v">${runway != null ? t("ui.forecast.runwayHours", { h: runway.toFixed(1) }) : t("ui.history.dash")}</div>
        </div>
        <div class="grid-compact">
          <div class="label">${t("ui.forecast.gridCompact")}</div>
          <div class="row" style="margin-top:6px">
            <span>
              ${present === true ? t("common.present") : present === false ? t("common.absent") : t("ui.history.dash")}
              ${uptime != null ? html` · ${uptime.toFixed(0)}% ${t("ui.grid.uptime24h")}` : null}
            </span>
            <button type="button" class="link-btn" @click=${this.goOverview}>${t("ui.forecast.fullStats")} →</button>
          </div>
        </div>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-forecast-insights": ForecastInsights;
  }
}
