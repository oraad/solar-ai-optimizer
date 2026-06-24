import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";

import { capabilityLabel } from "../field-labels.js";
import { sharedStyles } from "../styles.js";
import type { Decision, ExecutionResult, GridChargePlan, ShedResult } from "../types.js";

@customElement("solar-decision-panel")
export class DecisionPanel extends LitElement {
  static styles = [
    sharedStyles,
    css`
      .summary { color: var(--text); font-size: 0.9rem; line-height: 1.5; margin-bottom: 14px; }
      .rationale { color: var(--muted); font-size: 0.82rem; line-height: 1.5; margin: 4px 0 16px; }
      .stats {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
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
      .subhead {
        font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em;
        color: var(--muted); margin: 16px 0 8px;
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
    `,
  ];

  @property({ attribute: false }) decision: Decision | null = null;
  @property({ attribute: false }) results: ExecutionResult[] = [];
  @property({ attribute: false }) shedResults: ShedResult[] = [];

  private riskClass(score: number): string {
    if (score >= 0.66) return "risk-high";
    if (score >= 0.33) return "risk-mid";
    return "risk-low";
  }

  private gridChargeLabel(gc: GridChargePlan | null | undefined): string {
    if (!gc) return "--";
    if (gc.enabled && gc.target_amps > 0) return `${gc.target_amps.toFixed(0)} A`;
    return "OFF";
  }

  private appliedGridChargeAmps(): number | null {
    for (const r of this.results) {
      if (r.capability !== "max_grid_charge_current" || !r.applied) continue;
      if (typeof r.requested === "number") return r.requested;
    }
    return null;
  }

  render() {
    const d = this.decision;
    if (!d) return html`<div class="card"><h3>Decision &amp; rationale</h3><p class="label">Waiting for first decision...</p></div>`;
    const gc = d.grid_charge ?? null;
    const applied = this.appliedGridChargeAmps();
    return html`
      <div class="card">
        <h3>Decision &amp; rationale</h3>
        <div class="summary">${d.summary}</div>
        <div class="stats">
          <div class="stat"><div class="label">Target SOC</div><div class="v">${d.reserve.target_soc.toFixed(0)}%</div></div>
          <div class="stat"><div class="label">Solar-bridge</div><div class="v">${d.reserve.solar_bridge_soc.toFixed(0)}%</div></div>
          <div class="stat"><div class="label">Autonomy floor</div><div class="v">${d.reserve.autonomy_floor_soc.toFixed(0)}%</div></div>
          <div class="stat ${gc?.enabled ? "risk-low" : ""}">
            <div class="label">Grid charge</div>
            <div class="v">${this.gridChargeLabel(gc)}</div>
            ${applied != null && gc?.enabled
              ? html`<div class="label" style="margin-top:4px">Applied: ${applied.toFixed(0)} A</div>`
              : null}
          </div>
          <div class="stat ${this.riskClass(d.blackout_risk_score)}"><div class="label">Risk score</div><div class="v">${(d.blackout_risk_score * 100).toFixed(0)}%</div></div>
        </div>
        <div class="rationale">${d.reserve.rationale}</div>
        ${gc?.rationale
          ? html`
              <div class="subhead">Grid charge rationale</div>
              <div class="rationale">${gc.rationale}</div>
            `
          : null}
        <div class="subhead">Actions</div>
        <div class="chips">
          ${d.actions.length === 0
            ? html`<span class="label">No actions this cycle.</span>`
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
        ${d.shed_actions && d.shed_actions.length
          ? html`
              <div class="subhead">Load shedding</div>
              <div class="chips">
                ${d.shed_actions.map(
                  (s) => html`
                    <span class="chip" title=${s.reason}>
                      <span class="cap">${s.tier}</span>
                      <span class="val ${s.desired_on ? "on" : "off"}">${s.desired_on ? "ON" : "SHED"}</span>
                      <span class="why">${s.reason}</span>
                    </span>
                  `,
                )}
              </div>
            `
          : null}
        ${this.results.length
          ? html`
              <div class="subhead">Execution results</div>
              <div class="chips">
                ${this.results.map(
                  (r) => html`
                    <span class="chip" title=${r.skipped_reason || r.error || ""}>
                      <span class="cap">${r.capability}</span>
                      <span class="val ${r.verified ? "on" : "off"}">
                        ${r.applied ? (r.verified ? "verified" : "applied") : r.skipped_reason || "skipped"}
                      </span>
                    </span>
                  `,
                )}
              </div>
            `
          : null}
        ${this.shedResults.length
          ? html`
              <div class="subhead">Shed execution</div>
              <div class="chips">
                ${this.shedResults.map(
                  (r) => {
                    const extra =
                      r.skipped_reason === "was off before shed"
                        ? "was off before shed"
                        : (r.companions_restored?.length ?? 0) > 0
                          ? `companions: ${r.companions_restored!.join(", ")}`
                          : "";
                    const title = [r.skipped_reason, extra].filter(Boolean).join(" · ");
                    return html`
                    <span class="chip" title=${title}>
                      <span class="cap">${r.tier}</span>
                      <span class="val ${r.verified ? "on" : "off"}">
                        ${r.desired_on ? "ON" : "OFF"} ${r.verified ? "ok" : r.skipped_reason || "pending"}
                      </span>
                      ${extra ? html`<span class="why">${extra}</span>` : null}
                    </span>
                  `;
                  },
                )}
              </div>
            `
          : null}
        ${d.shadow_mode
          ? html`<p class="label" style="margin-top:12px">Shadow mode: actions are logged but NOT written to the inverter.</p>`
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
