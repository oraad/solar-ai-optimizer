import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

import { batteryEtaLine } from "../duration.js";
import { statusHelp } from "../field-help.js";
import { labelWithTip } from "../label-tip.js";
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
  reserve: "\u{1F6E1}",
  outdoor: "\u{1F321}",
  risk: "\u26A0",
} as const;

@customElement("solar-status-cards")
export class StatusCards extends LitElement {
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
        background: #2a313c;
        margin-top: 8px;
        overflow: hidden;
      }
      .soc-fill { height: 100%; background: linear-gradient(90deg, var(--good), var(--accent)); }
      .reserve-mark {
        position: absolute; top: -2px; width: 2px; height: 14px; background: var(--accent-2);
      }
      .eta { margin-top: 4px; font-size: 0.78rem; color: var(--muted); }
    `,
  ];

  @property({ attribute: false }) status: SystemStatus | null = null;

  @property({ attribute: false }) battery: BatteryConfigView | null = null;

  private tileHead(icon: string, label: string, helpKey: string) {
    return html`
      <div class="head">
        <span class="ic">${icon}</span>
        <span class="label">${labelWithTip(label, statusHelp(helpKey))}</span>
      </div>
    `;
  }

  render() {
    const t = this.status?.telemetry ?? null;
    const d = this.status?.decision ?? null;
    const soc = t?.battery_soc ?? null;
    const reserve = d?.reserve.target_soc ?? null;
    const battP = t?.battery_power ?? null;
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

    return html`
      <div class="card">
        <h3>Live status</h3>
        ${stale
          ? html`<p class="label" style="color:var(--bad)">
              Telemetry is stale${age != null ? ` (${Math.round(age)}s old)` : ""} —
              shedding and grid actions use conservative defaults.
            </p>`
          : null}
        <div class="tiles">
          <div class="tile">
            ${this.tileHead(STATUS_ICONS.solar, "Solar PV", "solar")}
            <div class="metric">${fmtW(t?.pv_power)}</div>
          </div>
          <div class="tile">
            ${this.tileHead(STATUS_ICONS.load, "Home load", "load")}
            <div class="metric">${fmtW(t?.load_power)}</div>
          </div>
          <div class="tile">
            ${this.tileHead(STATUS_ICONS.battery, "Battery", "battery")}
            <div class="metric">${soc != null ? `${soc.toFixed(0)}%` : "--"}</div>
            <div class="soc-bar">
              <div class="soc-fill" style="width:${soc ?? 0}%"></div>
              ${reserve != null
                ? html`<div class="reserve-mark" style="left:${reserve}%" title="Reserve target"></div>`
                : null}
            </div>
            <div class="label" style="margin-top:6px; color:${battColor}">
              ${battState || "--"} ${battP != null ? `(${fmtW(battP)})` : ""}
            </div>
            ${eta ? html`<div class="eta">${eta}</div>` : null}
          </div>
          <div class="tile">
            ${this.tileHead(STATUS_ICONS.grid, "Grid", "grid")}
            <div class="metric">
              <span class="pill ${t?.grid_present ? "good" : "muted"}">
                <span class="dot ${t?.grid_present ? "on" : "off"}"></span>
                ${t?.grid_present ? "present" : "absent"}
              </span>
            </div>
            <div class="label" style="margin-top:6px">${fmtW(t?.grid_power)}</div>
          </div>
          <div class="tile">
            ${this.tileHead(STATUS_ICONS.reserve, "Reserve target", "reserve")}
            <div class="metric">${reserve != null ? `${reserve.toFixed(0)}%` : "--"}</div>
          </div>
          ${t?.outdoor_temp != null
            ? html`<div class="tile">
                ${this.tileHead(STATUS_ICONS.outdoor, "Outdoor", "outdoor")}
                <div class="metric">${t.outdoor_temp.toFixed(1)}&deg;C</div>
              </div>`
            : null}
          ${t?.battery_temp != null
            ? html`<div class="tile">
                <div class="head"><span class="ic">${STATUS_ICONS.outdoor}</span><span class="label">Battery temp</span></div>
                <div class="metric">${t.battery_temp.toFixed(1)}&deg;C</div>
              </div>`
            : null}
          <div class="tile">
            ${this.tileHead(STATUS_ICONS.risk, "Blackout risk", "risk")}
            <div class="metric">
              ${d
                ? html`<span class="pill ${riskClass(d.blackout_risk)}">${d.blackout_risk}</span>`
                : "--"}
            </div>
          </div>
        </div>
      </div>
    `;
  }
}

function riskClass(r: string): string {
  switch (r) {
    case "low": return "good";
    case "moderate": return "warn";
    case "high": return "bad";
    case "critical": return "critical";
    default: return "muted";
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-status-cards": StatusCards;
  }
}
