import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

import { batteryEtaLine } from "../duration.js";
import { formatRiskFromLevel } from "../blackout-risk.js";
import { statusHelp } from "../field-help.js";
import { t } from "../i18n.js";
import { labelWithTip } from "../label-tip.js";
import { LocaleController } from "../locale-controller.js";
import { sharedStyles } from "../styles.js";
import "./info-tip.js";
import type { SystemStatus } from "../types.js";

export interface BatteryConfigView {
  capacity_kwh?: number;
  round_trip_efficiency?: number;
  max_soc_ceiling?: number;
  min_soc_floor?: number;
}

function fmtW(w: number | null | undefined): string {
  if (w == null) return "--";
  const kw = w / 1000;
  return Math.abs(kw) >= 1 ? `${kw.toFixed(2)} kW` : `${Math.round(w)} W`;
}

const STATUS_ICONS = {
  solar: "\u2600",
  load: "\u2302",
  battery: "\u{1F50B}",
  grid: "\u26A1",
  gridCharge: "\u{1F50C}",
  reserve: "\u{1F6E1}",
  outdoor: "\u{1F321}",
  batteryTemp: "\u2668",
  risk: "\u26A0",
} as const;

@customElement("solar-status-cards")
export class StatusCards extends LitElement {
  constructor() {
    super();
    new LocaleController(this);
  }

  static styles = [
    sharedStyles,
    css`
      .tiles {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 12px;
      }
      .tile {
        background: var(--panel-2);
        border: 1px solid var(--border);
        border-radius: var(--radius-sm);
        padding: 14px;
        transition: border-color 0.15s ease, transform 0.15s ease;
      }
      .tile:hover { border-color: var(--border-strong); transform: translateY(-2px); }
      .tile .head { display: flex; align-items: center; gap: 7px; margin-bottom: 6px; }
      .tile .head .ic {
        width: 22px; height: 22px; display: grid; place-items: center;
        border-radius: 6px; font-size: 0.85rem; background: var(--panel-3); color: var(--accent-2);
      }
      .tile .head .label { margin: 0; }
      .tile .metric { font-size: 1.5rem; }
      .soc-bar {
        position: relative;
        height: 10px;
        border-radius: 6px;
        background: var(--track);
        margin-top: 8px;
        overflow: hidden;
      }
      .soc-fill { height: 100%; background: linear-gradient(90deg, var(--good), var(--accent)); }
      .reserve-mark {
        position: absolute; top: -2px; width: 2px; height: 14px; background: var(--accent-2);
      }
      .eta { margin-top: 4px; font-size: 0.78rem; color: var(--muted); }
      .tiles.compact { grid-template-columns: repeat(4, 1fr); }
      @media (max-width: 700px) { .tiles.compact { grid-template-columns: repeat(2, 1fr); } }
      .skeleton-tile {
        background: var(--panel-2);
        border: 1px solid var(--border);
        border-radius: var(--radius-sm);
        padding: 14px;
        min-height: 72px;
      }
      .skeleton-line {
        height: 12px;
        border-radius: 4px;
        margin-bottom: 8px;
        background: linear-gradient(90deg, var(--panel-3) 25%, var(--panel-2) 50%, var(--panel-3) 75%);
        background-size: 200% 100%;
        animation: shimmer 1.2s infinite;
      }
      .skeleton-line.wide { width: 70%; height: 20px; }
      @keyframes shimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
    `,
  ];

  @property({ attribute: false }) status: SystemStatus | null = null;

  @property({ attribute: false }) battery: BatteryConfigView | null = null;

  @property({ type: Boolean }) compact = false;

  @property({ type: Boolean }) loading = false;

  private tileHead(icon: string, label: string, helpKey: string) {
    return html`
      <div class="head">
        <span class="ic">${icon}</span>
        <span class="label">${labelWithTip(label, statusHelp(helpKey))}</span>
      </div>
    `;
  }

  render() {
    if (this.loading && !this.status) {
      return html`
        <div class="card">
          <h3>${t("ui.status.liveStatus")}</h3>
          <div class="tiles compact">
            ${[1, 2, 3, 4].map(() => html`
              <div class="skeleton-tile">
                <div class="skeleton-line"></div>
                <div class="skeleton-line wide"></div>
              </div>
            `)}
          </div>
        </div>
      `;
    }

    const telemetry = this.status?.telemetry ?? null;
    const d = this.status?.decision ?? null;
    const soc = telemetry?.battery_soc ?? null;
    const reserve = d?.reserve.target_soc ?? null;
    const battP = telemetry?.battery_power ?? null;
    const battState =
      battP == null ? "" : battP > 20 ? "charging" : battP < -20 ? "discharging" : "idle";

    const battColor =
      battState === "charging" ? "var(--good)"
      : battState === "discharging" ? "var(--accent-2)"
      : "var(--muted)";

    const battSpec = this.status?.battery_summary ?? this.battery;
    const eta =
      battSpec && soc != null && battP != null
        ? batteryEtaLine({
            soc,
            powerW: battP,
            capacityKwh: battSpec.capacity_kwh ?? 0,
            roundTripEfficiency: battSpec.round_trip_efficiency ?? 0.9,
            maxSocCeiling: battSpec.max_soc_ceiling ?? 100,
            minSocFloor: battSpec.min_soc_floor ?? 20,
            targetSoc: d?.reserve.target_soc ?? null,
            autonomyFloorSoc: d?.reserve.autonomy_floor_soc ?? null,
          })
        : null;

    const stale = this.status?.telemetry_stale ?? false;
    const age = this.status?.telemetry_age_seconds;
    const gc = d?.grid_charge ?? null;
    const gridAbsent = telemetry?.grid_present === false;
    const gcAmps = gc?.target_amps;
    const gcEnabled = gc?.enabled === true && (gcAmps ?? 0) > 0;
    const gcMetric = gridAbsent
      ? "--"
      : gcEnabled
        ? `${gcAmps!.toFixed(0)} A`
        : gc
          ? t("common.off")
          : "--";
    const gcSub = gridAbsent
      ? t("ui.status.gridAbsent")
      : gc
        ? gc.enabled
          ? t("ui.status.gridChargeOn", { amps: gc.max_amps.toFixed(0) })
          : t("ui.status.gridChargeOff")
        : "";

    return html`
      <div class="card">
        <h3>${t("ui.status.liveStatus")}</h3>
        ${stale
          ? html`<p class="label" style="color:var(--bad)">
              ${t("ui.status.staleTelemetry", {
                age:
                  age != null
                    ? t("ui.status.staleAge", { s: String(Math.round(age)) })
                    : "",
              })}
            </p>`
          : null}
        <div class="tiles ${this.compact ? "compact" : ""}">
          <div class="tile">
            ${this.tileHead(STATUS_ICONS.solar, t("ui.status.solarPv"), "solar")}
            <div class="metric">${fmtW(telemetry?.pv_power)}</div>
          </div>
          <div class="tile">
            ${this.tileHead(STATUS_ICONS.load, t("ui.status.homeLoad"), "load")}
            <div class="metric">${fmtW(telemetry?.load_power)}</div>
          </div>
          <div class="tile">
            ${this.tileHead(STATUS_ICONS.battery, t("ui.status.battery"), "battery")}
            <div class="metric">${soc != null ? `${soc.toFixed(0)}%` : "--"}</div>
            <div class="soc-bar">
              <div class="soc-fill" style="width:${soc ?? 0}%"></div>
              ${reserve != null
                ? html`<div class="reserve-mark" style="left:${reserve}%" title=${t("ui.status.reserveMarkTitle")}></div>`
                : null}
            </div>
            <div class="label" style="margin-top:6px; color:${battColor}">
              ${battState ? t(`common.${battState}`) : "--"} ${battP != null ? `(${fmtW(battP)})` : ""}
            </div>
            ${eta ? html`<div class="eta">${eta}</div>` : null}
          </div>
          <div class="tile">
            ${this.tileHead(STATUS_ICONS.grid, t("ui.status.grid"), "grid")}
            <div class="metric">
              <span class="pill ${telemetry?.grid_present ? "good" : "muted"}">
                <span class="dot ${telemetry?.grid_present ? "on" : "off"}"></span>
                ${telemetry?.grid_present ? t("common.present") : t("common.absent")}
              </span>
            </div>
            <div class="label" style="margin-top:6px">${fmtW(telemetry?.grid_power)}</div>
          </div>
          ${this.compact
            ? null
            : html`
          <div class="tile">
            ${this.tileHead(STATUS_ICONS.gridCharge, t("ui.status.gridCharge"), "grid_charge")}
            <div class="metric" style="color:${gcEnabled ? "var(--good)" : "var(--muted)"}">
              ${gcMetric}
            </div>
            ${gcSub ? html`<div class="label" style="margin-top:6px">${gcSub}</div>` : null}
          </div>
          <div class="tile">
            ${this.tileHead(STATUS_ICONS.reserve, t("ui.status.reserveTarget"), "reserve")}
            <div class="metric">${reserve != null ? `${reserve.toFixed(0)}%` : "--"}</div>
          </div>
          ${telemetry?.outdoor_temp != null
            ? html`<div class="tile">
                ${this.tileHead(STATUS_ICONS.outdoor, t("ui.status.outdoor"), "outdoor")}
                <div class="metric">${telemetry.outdoor_temp.toFixed(1)}&deg;C</div>
              </div>`
            : null}
          ${telemetry?.battery_temp != null
            ? html`<div class="tile">
                ${this.tileHead(STATUS_ICONS.batteryTemp, t("ui.status.batteryTemp"), "battery_temp")}
                <div class="metric">${telemetry.battery_temp.toFixed(1)}&deg;C</div>
              </div>`
            : null}
          <div class="tile">
            ${this.tileHead(STATUS_ICONS.risk, t("ui.status.blackoutRisk"), "risk")}
            <div class="metric">
              ${d
                ? (() => {
                    const risk = formatRiskFromLevel(d.blackout_risk);
                    return html`<span class="pill ${risk.pillClass}">${risk.label}</span>`;
                  })()
                : "--"}
            </div>
          </div>
            `}
        </div>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-status-cards": StatusCards;
  }
}
