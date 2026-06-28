import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

import { capabilityLabel } from "../field-labels.js";
import { riskPillClassFromScore } from "../blackout-risk.js";
import { gridChargeLabel } from "../grid-charge-display.js";
import { t } from "../i18n.js";
import { LocaleController } from "../locale-controller.js";
import {
  groupShedActionsByTier,
  groupShedResultsByTier,
  shedActionTooltip,
  shedResultTooltip,
  type TierShedResultSummary,
} from "../shed-display.js";
import { sharedStyles } from "../styles.js";
import type { Decision, ExecutionResult, ShedResult, SystemStatus } from "../types.js";

@customElement("solar-decision-panel")
export class DecisionPanel extends LitElement {
  constructor() {
    super();
    new LocaleController(this);
  }

  static styles = [
    sharedStyles,
    css`
      .summary { color: var(--text); font-size: 0.9rem; line-height: 1.5; margin-bottom: 14px; }
      .rationale { color: var(--muted); font-size: 0.82rem; line-height: 1.5; margin: 4px 0 12px; }
      .stats {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 10px;
        margin-bottom: 14px;
      }
      @media (max-width: 700px) { .stats { grid-template-columns: repeat(2, 1fr); } }
      .stat {
        background: var(--panel-2); border: 1px solid var(--border);
        border-radius: var(--radius-sm); padding: 10px 12px;
      }
      .stat .v { font-size: 1.25rem; font-weight: 700; font-variant-numeric: tabular-nums; }
      .stat.risk-low .v { color: var(--good); }
      .stat.risk-mid .v { color: var(--warn); }
      .stat.risk-high .v { color: var(--bad); }
      details.details {
        border: 1px solid var(--border);
        border-radius: var(--radius-sm);
        padding: 10px 12px;
        margin-top: 8px;
      }
      details.details summary {
        cursor: pointer;
        font-size: 0.78rem;
        font-weight: 600;
        color: var(--muted);
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }
      .subhead {
        font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em;
        color: var(--muted); margin: 14px 0 8px;
      }
      .chips { display: flex; flex-wrap: wrap; gap: 8px; }
      .chip {
        display: inline-flex; align-items: center; gap: 8px;
        background: var(--panel-2); border: 1px solid var(--border);
        border-radius: 999px; padding: 6px 12px; font-size: 0.82rem;
      }
      .chip .cap { font-weight: 600; }
      .chip .val { color: var(--accent); font-weight: 700; }
      .chip .val.on { color: var(--good); }
      .chip .val.off { color: var(--bad); }
      .chip .why { color: var(--muted); }
      .shed-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; margin: 8px 0; }
      .shed-table th, .shed-table td { text-align: start; padding: 6px 8px; border-bottom: 1px solid var(--border); }
      .link-row { margin-top: 10px; display: flex; gap: 12px; flex-wrap: wrap; }
      .link-row button.link-btn {
        background: none; border: none; color: var(--accent);
        padding: 0; font-size: 0.82rem; font-weight: 600; cursor: pointer;
      }
      .link-row button.link-btn:hover { text-decoration: underline; }
    `,
  ];

  @property({ attribute: false }) decision: Decision | null = null;
  @property({ attribute: false }) results: ExecutionResult[] = [];
  @property({ attribute: false }) shedResults: ShedResult[] = [];
  @property({ attribute: false }) status: SystemStatus | null = null;
  @property({ type: String }) role: "admin" | "viewer" = "admin";

  private riskStatClass(score: number): string {
    const cls = riskPillClassFromScore(score);
    if (cls === "bad") return "risk-high";
    if (cls === "warn") return "risk-mid";
    return "risk-low";
  }

  private appliedGridChargeAmps(): number | null {
    for (const r of this.results) {
      if (r.capability !== "max_grid_charge_current" || !r.applied) continue;
      if (typeof r.requested === "number") return r.requested;
    }
    return null;
  }

  private skipLabel(r: ExecutionResult | ShedResult): string {
    return r.skipped_reason_text ?? r.skipped_reason ?? t("ui.decision.skipped");
  }

  private tierSkipLabel(summary: TierShedResultSummary): string {
    return (
      summary.uniformSkipReasonText ??
      summary.primarySkipReasonText ??
      summary.uniformSkipReason ??
      summary.primarySkipReason ??
      t("ui.decision.skipped")
    );
  }

  private tierShedExtra(summary: TierShedResultSummary): string {
    if (summary.wasOffBeforeShed) return t("ui.decision.wasOffBeforeShed");
    if (summary.companionsRestored.length > 0) {
      return t("ui.decision.companions", { list: summary.companionsRestored.join(", ") });
    }
    return "";
  }

  private goHistoryShed(): void {
    window.dispatchEvent(
      new CustomEvent("solar-navigate-tab", {
        detail: { tab: "history", history: { view: "activity", activity: "shed" } },
        bubbles: true,
        composed: true,
      }),
    );
  }

  private goLoadShedding(): void {
    window.dispatchEvent(
      new CustomEvent("solar-navigate-tab", { detail: "load_shedding", bubbles: true, composed: true }),
    );
  }

  private renderShedSection(d: Decision) {
    if (!d.shed_actions?.length) return null;
    const grouped = groupShedActionsByTier(d.shed_actions);
    const useTable = grouped.length > 3;
    return html`
      <div class="subhead">${t("ui.decision.loadShedding")}</div>
      ${useTable
        ? html`
            <table class="shed-table">
              <thead>
                <tr><th>${t("ui.history.colTier")}</th><th>${t("ui.history.colDesired")}</th><th>${t("ui.history.colSummary")}</th></tr>
              </thead>
              <tbody>
                ${grouped.map(
                  (s) => html`
                    <tr title=${shedActionTooltip(s, t("common.on"), t("ui.decision.shed"))}>
                      <td>${s.tier}</td>
                      <td><span class="pill ${s.desired_on ? "good" : "bad"}">${s.desired_on ? t("common.on") : t("ui.decision.shed")}</span></td>
                      <td>${s.reason}</td>
                    </tr>
                  `,
                )}
              </tbody>
            </table>
          `
        : html`
            <div class="chips">
              ${grouped.map(
                (s) => html`
                  <span class="chip" title=${shedActionTooltip(s, t("common.on"), t("ui.decision.shed"))}>
                    <span class="cap">${s.tier}</span>
                    <span class="val ${s.desired_on ? "on" : "off"}">${s.desired_on ? t("common.on") : t("ui.decision.shed")}</span>
                    <span class="why">${s.reason}</span>
                  </span>
                `,
              )}
            </div>
          `}
      <div class="link-row">
        <button type="button" class="link-btn" @click=${this.goHistoryShed}>${t("ui.decision.viewShedHistory")} →</button>
        ${this.role === "admin"
          ? html`<button type="button" class="link-btn" @click=${this.goLoadShedding}>${t("ui.decision.configureShedding")} →</button>`
          : null}
      </div>
    `;
  }

  render() {
    const d = this.decision;
    if (!d) return html`<div class="card"><h3>${t("ui.decision.title")}</h3><p class="label">${t("ui.decision.waiting")}</p></div>`;
    const engineOn = this.status?.engine_enabled !== false;
    const gridOn = this.status?.grid_charge_enabled !== false;
    const gc = d.grid_charge ?? null;
    const applied = this.appliedGridChargeAmps();
    const showAutonomy = engineOn && d.reserve.autonomy_floor_soc !== d.reserve.target_soc;
    const hasDetails =
      (engineOn && d.reserve.rationale) ||
      (gridOn && gc?.rationale) ||
      (gridOn && d.actions.length > 0) ||
      (d.shed_actions?.length ?? 0) > 0 ||
      this.results.length > 0 ||
      this.shedResults.length > 0 ||
      showAutonomy;

    return html`
      <div class="card">
        <h3>${t("ui.decision.title")}</h3>
        <div class="summary">${d.summary}</div>
        ${engineOn || gridOn
          ? html`<div class="stats">
          ${engineOn
            ? html`
                <div class="stat"><div class="label">${t("ui.decision.targetSoc")}</div><div class="v">${d.reserve.target_soc.toFixed(0)}%</div></div>
                <div class="stat"><div class="label">${t("ui.decision.solarBridge")}</div><div class="v">${d.reserve.solar_bridge_soc.toFixed(0)}%</div></div>
              `
            : null}
          ${gridOn
            ? html`<div class="stat ${gc?.enabled ? "risk-low" : ""}">
            <div class="label">${t("ui.decision.gridCharge")}</div>
            <div class="v">${gridChargeLabel(gc)}</div>
            ${applied != null && gc?.enabled
              ? html`<div class="label" style="margin-top:4px">${t("ui.decision.applied", { amps: applied.toFixed(0) })}</div>`
              : null}
          </div>`
            : null}
          ${engineOn
            ? html`<div class="stat ${this.riskStatClass(d.blackout_risk_score)}"><div class="label">${t("ui.decision.riskScore")}</div><div class="v">${(d.blackout_risk_score * 100).toFixed(0)}%</div></div>`
            : null}
        </div>`
          : null}

        ${hasDetails
          ? html`
              <details class="details">
                <summary>${t("ui.decision.details")}</summary>
                ${showAutonomy
                  ? html`<div class="label" style="margin-top:8px">${t("ui.decision.autonomyFloor")}: ${d.reserve.autonomy_floor_soc.toFixed(0)}%</div>`
                  : null}
                ${d.reserve.rationale ? html`<div class="rationale">${d.reserve.rationale}</div>` : null}
                ${gc?.rationale
                  ? html`
                      <div class="subhead">${t("ui.decision.gridChargeRationale")}</div>
                      <div class="rationale">${gc.rationale}</div>
                    `
                  : null}
                ${gridOn
                  ? html`
                      <div class="subhead">${t("ui.decision.actions")}</div>
                      <div class="chips">
                        ${d.actions.length === 0
                          ? html`<span class="label">${t("ui.decision.noActions")}</span>`
                          : d.actions.map(
                              (a) => html`
                                <span class="chip" title=${a.reason}>
                                  <span class="cap">${capabilityLabel(a.capability)}</span>
                                  <span class="val">${String(a.value)}</span>
                                  <span class="why">${a.reason}</span>
                                </span>
                              `,
                            )}
                      </div>
                    `
                  : null}
                ${this.renderShedSection(d)}
                ${this.results.length
                  ? html`
                      <div class="subhead">${t("ui.decision.executionResults")}</div>
                      <div class="chips">
                        ${this.results.map(
                          (r) => html`
                            <span class="chip" title=${this.skipLabel(r) || r.error || ""}>
                              <span class="cap">${capabilityLabel(r.capability)}</span>
                              <span class="val ${r.verified ? "on" : "off"}">
                                ${r.applied ? (r.verified ? t("ui.decision.verified") : t("ui.decision.appliedShort")) : this.skipLabel(r)}
                              </span>
                            </span>
                          `,
                        )}
                      </div>
                    `
                  : null}
                ${this.shedResults.length
                  ? html`
                      <div class="subhead">${t("ui.decision.shedExecution")}</div>
                      <div class="chips">
                        ${groupShedResultsByTier(this.shedResults).map((s) => {
                          const extra = this.tierShedExtra(s);
                          const status = s.allVerified
                            ? t("ui.decision.ok")
                            : this.tierSkipLabel(s) || t("ui.decision.pending");
                          return html`
                            <span class="chip" title=${shedResultTooltip(s)}>
                              <span class="cap">${s.tier}</span>
                              <span class="val ${s.allVerified ? "on" : "off"}">
                                ${s.desired_on ? t("common.on") : t("common.off")} ${status}
                              </span>
                              ${extra ? html`<span class="why">${extra}</span>` : null}
                            </span>
                          `;
                        })}
                      </div>
                    `
                  : null}
              </details>
            `
          : null}
        ${d.shadow_mode
          ? html`<p class="label" style="margin-top:12px">${t("ui.decision.shadowMode")}</p>`
          : null}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-decision-panel": DecisionPanel;
  }
}
