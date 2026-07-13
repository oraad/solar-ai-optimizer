import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";

import { capabilityLabel } from "../field-labels.js";
import { riskPillClassFromScore } from "../blackout-risk.js";
import { gridChargeLabel } from "../grid-charge-display.js";
import { statusHelp } from "../field-help.js";
import { labelWithTip } from "../label-tip.js";
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
import { api } from "../api.js";
import type {
  Decision,
  ExecutionResult,
  ExecutionSummary,
  ExplanationStep,
  ShedResult,
  SystemStatus,
} from "../types.js";

@customElement("solar-decision-panel")
export class DecisionPanel extends LitElement {
  constructor() {
    super();
    new LocaleController(this);
  }

  static styles = [
    sharedStyles,
    css`
      .summary { color: var(--text); font-size: 0.9rem; line-height: 1.5; margin-bottom: 12px; }
      .rationale { color: var(--muted); font-size: 0.82rem; line-height: 1.5; margin: 4px 0 12px; }
      .banner {
        border: 1px solid var(--border); border-radius: var(--radius-sm);
        padding: 8px 10px; margin-bottom: 12px; font-size: 0.82rem; color: var(--muted);
        background: var(--panel-2);
      }
      .banner.warn { border-color: color-mix(in srgb, var(--warn) 50%, var(--border)); color: var(--warn); }
      .why-list { margin: 0 0 14px; padding-inline-start: 1.1rem; }
      .why-list li { margin: 4px 0; font-size: 0.86rem; line-height: 1.45; color: var(--text); }
      .why-list .outcome { color: var(--accent); font-weight: 600; margin-inline-start: 4px; }
      .mods { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
      .verify {
        display: grid; gap: 8px; margin-bottom: 12px;
      }
      .verify-row {
        display: grid;
        grid-template-columns: 1.1fr 1fr 1fr;
        gap: 8px;
        align-items: center;
        background: var(--panel-2);
        border: 1px solid var(--border);
        border-radius: var(--radius-sm);
        padding: 8px 10px;
        font-size: 0.82rem;
      }
      .verify-row.diff { border-color: color-mix(in srgb, var(--warn) 55%, var(--border)); }
      .verify-row .label { font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; font-size: 0.72rem; }
      .verify-row .val { font-variant-numeric: tabular-nums; font-weight: 700; }
      .verify-row .st { color: var(--muted); }
      .verify-row .st.ok { color: var(--good); }
      .verify-row .st.warn { color: var(--warn); }
      .verify-row .st.bad { color: var(--bad); }
      @media (max-width: 700px) {
        .verify-row { grid-template-columns: 1fr; gap: 2px; }
      }
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
      .why-more {
        background: none; border: none; color: var(--muted); font-size: 0.82rem;
        padding: 0; cursor: pointer; font-weight: 600; margin-bottom: 10px;
      }
      .why-more:hover { color: var(--accent); }
      .skeleton {
        border-radius: var(--radius-sm);
        background: linear-gradient(90deg, var(--panel-2) 25%, var(--panel) 50%, var(--panel-2) 75%);
        background-size: 200% 100%;
        animation: shimmer 1.5s infinite;
      }
      @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
      .skeleton-line { height: 0.85em; border-radius: 4px; margin: 6px 0; }
      .skeleton-line.w-full { width: 100%; }
      .skeleton-line.w-3\/4 { width: 75%; }
      .skeleton-line.w-1\/2 { width: 50%; }
      @media (prefers-reduced-motion: reduce) {
        .skeleton { animation: none; background: var(--panel-2); }
      }
      .forensics {
        margin-top: 12px; border: 1px solid var(--border); border-radius: var(--radius-sm);
        padding: 10px 12px; background: var(--panel-2); font-size: 0.78rem;
        max-height: 360px; overflow: auto; white-space: pre-wrap; color: var(--muted);
      }
    `,
  ];

  @property({ attribute: false }) decision: Decision | null = null;
  @property({ attribute: false }) results: ExecutionResult[] = [];
  @property({ attribute: false }) shedResults: ShedResult[] = [];
  @property({ attribute: false }) status: SystemStatus | null = null;
  @property({ attribute: false }) planCycleId: string | null = null;
  @property({ type: Boolean }) planLoading = false;
  @property({ type: String }) role: "admin" | "viewer" = "admin";
  /** Set when the user deep-linked to a specific historical decision (#overview/decision/{id}).
   * Takes precedence over `decision` while set, so the pinned cycle stays visible. */
  @property({ attribute: false }) deepLinkDecision: Decision | null = null;
  /** True when a deep-linked decision id could not be found in history. */
  @property({ type: Boolean }) deepLinkNotFound = false;

  @state() private forensicsOpen = false;
  @state() private forensicsText = "";
  @state() private forensicsLoading = false;
  @state() private whyExpanded = false;

  private riskStatClass(score: number): string {
    const cls = riskPillClassFromScore(score);
    if (cls === "bad") return "risk-high";
    if (cls === "warn") return "risk-mid";
    return "risk-low";
  }

  private verificationMatched(): boolean {
    const d = this.decision;
    if (!d?.cycle_id) return true;
    if (!this.planCycleId) return this.results.length > 0 || this.shedResults.length > 0;
    return d.cycle_id === this.planCycleId;
  }

  private appliedGridChargeAmps(): number | null {
    const summary = this.status?.execution_summary;
    if (summary?.applied_grid_charge_amps != null) return summary.applied_grid_charge_amps;
    for (const r of this.results) {
      if (r.capability !== "max_grid_charge_current") continue;
      if ((r.applied || r.verified) && typeof r.requested === "number") return r.requested;
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

  private stepText(step: ExplanationStep): string {
    if (step.detail) return step.detail;
    if (step.title && step.outcome) return `${step.title}: ${step.outcome}`;
    if (step.title) return step.title;
    const key = step.detail_key || step.title_key;
    const localized = t(key, step.params ?? {});
    if (localized !== key) return localized;
    if (step.outcome) return `${step.id}: ${step.outcome}`;
    return step.id;
  }

  private whyBullets(d: Decision): string[] {
    const steps = d.explanation?.steps ?? [];
    const preferred = ["reserve", "grid_charge", "risk"];
    const ordered = [
      ...preferred.map((id) => steps.find((s) => s.id === id)).filter(Boolean),
      ...steps.filter((s) => !preferred.includes(s.id)),
    ] as ExplanationStep[];
    const bullets = ordered.map((s) => this.stepText(s));
    if (bullets.length) return bullets;
    const fallback: string[] = [];
    if (d.reserve.rationale) fallback.push(d.reserve.rationale);
    if (d.grid_charge?.rationale) fallback.push(d.grid_charge.rationale);
    if (!fallback.length) fallback.push(t("ui.decision.whyWaiting"));
    return fallback;
  }

  private modifierPills(d: Decision) {
    const pills: { label: string; cls: string }[] = [];
    if (d.shadow_mode) pills.push({ label: t("ui.decision.modShadow"), cls: "warn" });
    if (this.status?.paused_grid_charge || this.status?.paused_shedding || this.status?.paused_optimization) {
      pills.push({ label: t("ui.decision.modWritesPaused"), cls: "warn" });
    }
    if (this.status?.reserve_soc_override != null) {
      pills.push({
        label: t("ui.decision.modReservePin", { pct: this.status.reserve_soc_override }),
        cls: "muted",
      });
    }
    if (this.status?.force_grid_charge_override === true) {
      pills.push({ label: t("ui.decision.modForceGc"), cls: "muted" });
    }
    const source = d.reserve.source ?? d.explanation?.reserve?.source;
    if (source && source !== "rules") {
      pills.push({ label: t("ui.decision.modSource", { source }), cls: "muted" });
    }
    return pills;
  }

  private gcStatusLabel(summary: ExecutionSummary | null | undefined, matched: boolean): { text: string; cls: string } {
    if (this.planLoading || !matched) return { text: t("ui.decision.verifyUpdating"), cls: "warn" };
    if (this.status?.shadow_mode || this.decision?.shadow_mode) {
      return { text: t("ui.decision.verifyShadow"), cls: "warn" };
    }
    const st = summary?.grid_charge_status ?? "";
    if (st === "paused" || !summary?.grid_charge_writes_allowed) {
      return { text: t("ui.decision.verifyPaused"), cls: "warn" };
    }
    if (st === "verified") return { text: t("ui.decision.verified"), cls: "ok" };
    if (st === "applied") return { text: t("ui.decision.appliedShort"), cls: "ok" };
    if (st === "skipped") return { text: t("ui.decision.skipped"), cls: "warn" };
    if (st === "error") return { text: t("ui.decision.verifyError"), cls: "bad" };
    if (st === "shadow") return { text: t("ui.decision.verifyShadow"), cls: "warn" };
    return { text: t("ui.decision.verifyNone"), cls: "" };
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

  private goHistoryRelated(): void {
    const cycleId = this.decision?.cycle_id;
    window.dispatchEvent(
      new CustomEvent("solar-navigate-tab", {
        detail: {
          tab: "history",
          history: { view: "activity", activity: "executions", cycleId: cycleId ?? undefined },
        },
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

  private async toggleForensics(): Promise<void> {
    if (this.forensicsOpen) {
      this.forensicsOpen = false;
      return;
    }
    this.forensicsOpen = true;
    this.forensicsLoading = true;
    try {
      const trace = await api.debugTrace("inputs,engine,overrides,causality,decision,execution");
      this.forensicsText = JSON.stringify(trace, null, 2);
    } catch (e) {
      this.forensicsText = String(e);
    } finally {
      this.forensicsLoading = false;
    }
  }

  private renderVerify(d: Decision) {
    const matched = this.verificationMatched();
    const summary = this.status?.execution_summary;
    const intendedReserve = `${d.reserve.target_soc.toFixed(0)}%`;
    const appliedReserve = intendedReserve; // reserve is a target, not an HA write
    const reserveStatus = matched
      ? t("ui.decision.verifyTarget")
      : t("ui.decision.verifyUpdating");

    const intendedGc =
      d.grid_charge == null
        ? "—"
        : d.grid_charge.enabled
          ? `${d.grid_charge.target_amps.toFixed(0)} A`
          : t("common.off");
    const appliedAmps = this.appliedGridChargeAmps();
    const appliedGc =
      !matched || this.planLoading
        ? "…"
        : appliedAmps != null
          ? `${appliedAmps.toFixed(0)} A`
          : d.grid_charge?.enabled
            ? "—"
            : t("common.off");
    const gcSt = this.gcStatusLabel(summary, matched);
    const gcDiff =
      matched &&
      appliedAmps != null &&
      d.grid_charge?.enabled === true &&
      Math.abs(appliedAmps - d.grid_charge.target_amps) > 0.5;

    return html`
      <div class="subhead">${t("ui.decision.verification")}</div>
      <div class="verify">
        <div class="verify-row">
          <div>
            <div class="label">${labelWithTip(t("ui.decision.targetSoc"), statusHelp("reserve"))}</div>
            <div class="val">${intendedReserve}</div>
          </div>
          <div>
            <div class="label">${t("ui.decision.verifyIntended")}</div>
            <div class="val">${intendedReserve}</div>
          </div>
          <div>
            <div class="label">${t("ui.decision.verifyStatus")}</div>
            <div class="st">${reserveStatus} · ${appliedReserve}</div>
          </div>
        </div>
        ${this.status?.grid_charge_enabled !== false
          ? html`
              <div class="verify-row ${gcDiff ? "diff" : ""}">
                <div>
                  <div class="label">${labelWithTip(t("ui.decision.gridCharge"), statusHelp("grid_charge"))}</div>
                  <div class="val">${intendedGc}</div>
                </div>
                <div>
                  <div class="label">${t("ui.decision.verifyApplied")}</div>
                  <div class="val">${appliedGc}</div>
                </div>
                <div>
                  <div class="label">${t("ui.decision.verifyStatus")}</div>
                  <div class="st ${gcSt.cls}">${gcSt.text}</div>
                </div>
              </div>
            `
          : nothing}
      </div>
    `;
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
          : html`<button type="button" class="link-btn" @click=${this.goLoadShedding}>${t("ui.decision.viewShedding")} →</button>`}
      </div>
    `;
  }

  private renderSkeleton() {
    return html`
      <div class="card">
        <h3>${t("ui.decision.title")}</h3>
        <div class="skeleton skeleton-line w-3/4" style="height:1.1em;margin-bottom:14px"></div>
        <div class="skeleton skeleton-line w-full"></div>
        <div class="skeleton skeleton-line w-3/4"></div>
        <div class="skeleton skeleton-line w-1/2"></div>
      </div>
    `;
  }

  render() {
    const d = this.deepLinkDecision ?? this.decision;
    if (!d) {
      if (this.deepLinkNotFound) {
        return html`<div class="card"><h3>${t("ui.decision.title")}</h3><div class="banner warn">${t("ui.decision.deepLinkNotFound")}</div></div>`;
      }
      if (this.planLoading) return this.renderSkeleton();
      return html`<div class="card"><h3>${t("ui.decision.title")}</h3><p class="label">${t("ui.decision.waiting")}</p></div>`;
    }
    const engineOn = this.status?.engine_enabled !== false;
    const gridOn = this.status?.grid_charge_enabled !== false;
    const gc = d.grid_charge ?? null;
    const showAutonomy = engineOn && d.reserve.autonomy_floor_soc !== d.reserve.target_soc;
    const mods = this.modifierPills(d);
    const why = this.whyBullets(d);
    const binding = gc?.cap_chain?.find((c) => c.binding);

    return html`
      <div class="card">
        <h3>${t("ui.decision.title")}</h3>
        ${this.deepLinkDecision
          ? html`<div class="banner">${t("ui.decision.deepLinkViewing")}</div>`
          : nothing}
        ${d.shadow_mode
          ? html`<div class="banner warn">${t("ui.decision.shadowMode")}</div>`
          : nothing}
        <div class="summary">${d.summary}</div>

        <div class="subhead">${t("ui.decision.why")}</div>
        <ul class="why-list">
          ${(this.whyExpanded ? why : why.slice(0, 3)).map((b) => html`<li>${b}</li>`)}
        </ul>
        ${why.length > 3
          ? html`<button
              type="button"
              class="why-more"
              @click=${() => { this.whyExpanded = !this.whyExpanded; }}
            >${this.whyExpanded
              ? t("ui.decision.showLess")
              : t("ui.decision.showMore", { n: String(why.length - 3) })}</button>`
          : null}

        ${mods.length
          ? html`<div class="mods">${mods.map((m) => html`<span class="pill ${m.cls}">${m.label}</span>`)}</div>`
          : nothing}

        ${this.renderVerify(d)}

        ${engineOn || gridOn
          ? html`<div class="stats">
          ${engineOn
            ? html`
                <div class="stat">
                  <div class="label">${labelWithTip(t("ui.decision.targetSoc"), statusHelp("reserve"))}</div>
                  <div class="v">${d.reserve.target_soc.toFixed(0)}%</div>
                </div>
                <div class="stat">
                  <div class="label">${labelWithTip(t("ui.decision.solarBridge"), statusHelp("reserve"))}</div>
                  <div class="v">${d.reserve.solar_bridge_soc.toFixed(0)}%</div>
                </div>
              `
            : null}
          ${gridOn
            ? html`<div class="stat ${gc?.enabled ? "risk-low" : ""}">
            <div class="label">${labelWithTip(t("ui.decision.gridCharge"), statusHelp("grid_charge"))}</div>
            <div class="v">${gridChargeLabel(gc)}</div>
          </div>`
            : null}
          ${engineOn
            ? html`<div class="stat ${this.riskStatClass(d.blackout_risk_score)}">
                <div class="label">${labelWithTip(t("ui.decision.riskScore"), statusHelp("risk"))}</div>
                <div class="v">${(d.blackout_risk_score * 100).toFixed(0)}%</div>
              </div>`
            : null}
        </div>`
          : null}

        <details class="details">
          <summary>${t("ui.decision.detailsRationale")}</summary>
          ${showAutonomy
            ? html`<div class="label" style="margin-top:8px">${labelWithTip(t("ui.decision.autonomyFloor"), statusHelp("reserve"))}: ${d.reserve.autonomy_floor_soc.toFixed(0)}%</div>`
            : null}
          ${d.reserve.rationale ? html`<div class="rationale">${d.reserve.rationale}</div>` : null}
          ${gc?.rationale
            ? html`
                <div class="subhead">${t("ui.decision.gridChargeRationale")}</div>
                <div class="rationale">${gc.rationale}</div>
              `
            : null}
          ${binding
            ? html`<div class="label">${t("ui.decision.bindingCap", {
                factor: binding.factor,
                amps: binding.ceiling_a.toFixed(0),
              })}</div>`
            : null}
          ${gc?.cap_chain?.length
            ? html`
                <div class="subhead">${t("ui.decision.capChain")}</div>
                <div class="chips">
                  ${gc.cap_chain.map(
                    (c) => html`
                      <span class="chip">
                        <span class="cap">${c.factor}</span>
                        <span class="val">${c.ceiling_a.toFixed(0)} A</span>
                        ${c.binding ? html`<span class="why">${t("ui.decision.binding")}</span>` : nothing}
                      </span>
                    `,
                  )}
                </div>
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
          ${d.cycle_id
            ? html`
                <div class="link-row">
                  <button type="button" class="link-btn" @click=${this.goHistoryRelated}>
                    ${t("ui.decision.relatedWrites")} →
                  </button>
                </div>
              `
            : nothing}
        </details>

        ${this.role === "admin"
          ? html`
              <div class="link-row">
                <button type="button" class="link-btn" @click=${this.toggleForensics}>
                  ${this.forensicsOpen ? t("ui.decision.hideForensics") : t("ui.decision.liveForensics")}
                </button>
              </div>
              ${this.forensicsOpen
                ? html`<div class="forensics" role="region" aria-label=${t("ui.decision.liveForensics")}>
                    ${this.forensicsLoading ? t("ui.decision.forensicsLoading") : this.forensicsText}
                  </div>`
                : nothing}
            `
          : nothing}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-decision-panel": DecisionPanel;
  }
}
