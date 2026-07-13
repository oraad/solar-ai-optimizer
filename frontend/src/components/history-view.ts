import { LitElement, css, html, type PropertyValues } from "lit";
import { customElement, property, query, state } from "lit/decorators.js";
import type uPlot from "uplot";

import { api } from "../api.js";
import { formatRiskFromDecision } from "../blackout-risk.js";
import { bindChartLifecycle } from "../chart-lifecycle.js";
import {
  chartContainerStyles,
  chartAxisPaddingRight,
  chartHeight,
  cssVar,
  gridAbsentBandHooks,
  gridAbsentIntervals,
  makeChart,
  scheduleChartRender,
  type ChartHandle,
} from "../charts.js";
import { formatDateTime, getDateFormat } from "../date-format.js";
import { entityDisplayName } from "../entity-resolve.js";
import { capabilityLabel } from "../field-labels.js";
import { dedupeConsecutiveExecutions, dedupeConsecutiveShedExecutions } from "../history-audit.js";
import { t } from "../i18n.js";
import { LocaleController } from "../locale-controller.js";
import {
  groupShedResultsByTier,
  shedResultTooltip,
  type TierShedResultSummary,
} from "../shed-display.js";
import { sharedStyles } from "../styles.js";
import type {
  DecisionHistoryRow,
  EntityInfo,
  ExecutionHistoryRow,
  GridEventRow,
  ShedExecutionRow,
  ShedResult,
  Telemetry,
} from "../types.js";

type HistoryViewTab = "timeline" | "decisions" | "activity";
type ActivityTab = "executions" | "shed" | "grid";

export type HistoryNavHint = {
  view?: HistoryViewTab;
  activity?: ActivityTab;
  cycleId?: string;
};

@customElement("solar-history-view")
export class HistoryView extends LitElement {
  constructor() {
    super();
    new LocaleController(this);
  }

  static styles = [
    sharedStyles,
    chartContainerStyles,
    css`
      .head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
      .tabs {
        display: flex;
        gap: 6px;
        margin-bottom: 12px;
        overflow-x: auto;
        flex-wrap: nowrap;
        -webkit-overflow-scrolling: touch;
      }
      .tabs button {
        padding: 6px 12px;
        border-radius: 6px;
        border: 1px solid var(--border);
        background: var(--panel-2);
        cursor: pointer;
        flex-shrink: 0;
        white-space: nowrap;
      }
      @media (max-width: 760px) {
        .tabs button { min-height: 44px; padding: 8px 14px; }
      }
      .tabs button.active { border-color: var(--accent); color: var(--accent); }
      .activity-seg {
        display: flex;
        gap: 6px;
        margin-bottom: 12px;
        flex-wrap: wrap;
      }
      .activity-seg button {
        padding: 5px 10px;
        border-radius: 6px;
        border: 1px solid var(--border);
        background: var(--panel-2);
        cursor: pointer;
        font-size: 0.78rem;
      }
      .activity-seg button.active { border-color: var(--accent-2); color: var(--accent-2); }
      .link-btn {
        background: none; border: none; color: var(--accent);
        padding: 0; font-size: 0.82rem; font-weight: 600; cursor: pointer;
      }
      .cycle-filter {
        font-size: 0.82rem; color: var(--muted); margin-bottom: 10px;
        display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
      }
      .legend { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 8px; flex-shrink: 0; }
      .swatch { display: inline-flex; align-items: center; gap: 6px; font-size: 0.78rem; color: var(--muted); }
      .swatch i { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
      .cursor-values { min-height: 1.2em; font-size: 0.78rem; color: var(--muted); margin-bottom: 6px; font-variant-numeric: tabular-nums; flex-shrink: 0; }
      select { margin-inline-start: 8px; }
      .table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; max-height: min(60vh, 560px); overflow-y: auto; }
      .table { width: 100%; border-collapse: collapse; font-size: 0.82rem; min-width: 480px; }
      .table thead th {
        position: sticky;
        top: 0;
        z-index: 1;
        background: var(--panel);
        box-shadow: 0 1px 0 var(--border);
      }
      .table th, .table td { text-align: start; padding: 6px 8px; border-bottom: 1px solid var(--border); }
      .table tr:hover { background: var(--panel-2); }
      .table tr.expandable { cursor: pointer; }
      .expanded-row td { background: var(--panel-2); font-size: 0.78rem; color: var(--muted); }
      .load-error {
        padding: 10px 12px;
        border-radius: var(--radius-sm);
        margin-bottom: 12px;
        font-size: 0.82rem;
        border: 1px solid var(--border);
        background: color-mix(in srgb, var(--bad) 12%, var(--panel-2));
        color: var(--bad);
      }
      .recent-strip {
        margin-top: 10px;
        font-size: 0.78rem;
        color: var(--muted);
        display: flex;
        flex-wrap: wrap;
        gap: 6px 12px;
      }
      .recent-strip .ev { white-space: nowrap; }
      .load-more-row { display: flex; justify-content: center; margin-top: 10px; }
      .load-more-row button:disabled { opacity: 0.5; cursor: not-allowed; }
    `,
  ];

  @state() private hours = 24;
  @state() private tab: HistoryViewTab = "timeline";
  @state() private activityTab: ActivityTab = "executions";
  @state() private cycleFilter: string | null = null;
  @state() private rows: Telemetry[] = [];
  @state() private decisions: DecisionHistoryRow[] = [];
  @state() private gridEvents: GridEventRow[] = [];
  @state() private executions: ExecutionHistoryRow[] = [];
  @state() private shedExecs: ShedExecutionRow[] = [];
  @state() private executionsCursor: string | null = null;
  @state() private shedExecsCursor: string | null = null;
  @state() private executionsLoadingMore = false;
  @state() private shedExecsLoadingMore = false;
  @state() private loadError = "";
  @state() private expandedDecisionTs = "";
  @state() private expandedActivityKey = "";
  @property({ attribute: false }) entities: EntityInfo[] = [];
  @property({ attribute: false }) navHint: HistoryNavHint | null = null;
  @query(".chart-mount") private chartEl!: HTMLDivElement;
  @query(".cursor-values") private cursorLegendEl!: HTMLDivElement;
  private chartHandle?: ChartHandle;
  private chartHasTemp: boolean | null = null;
  private forceChartRecreate = false;
  private chartRenderLock = false;
  private pollTimer?: number;
  private unbindLifecycle?: () => void;

  private dateFmt() {
    return getDateFormat();
  }

  private queueRenderChart(): void {
    scheduleChartRender(() => {
      if (this.chartRenderLock) return;
      this.chartRenderLock = true;
      try {
        this.renderChart();
      } finally {
        this.chartRenderLock = false;
      }
    });
  }

  connectedCallback(): void {
    super.connectedCallback();
    this.applyNavHint(this.navHint);
    this.unbindLifecycle = bindChartLifecycle(this, {
      onThemeChange: () => {
        this.forceChartRecreate = true;
        this.queueRenderChart();
      },
      onDateFormatChange: () => {
        this.forceChartRecreate = true;
        this.queueRenderChart();
        this.requestUpdate();
      },
      onLocaleChange: () => {
        this.forceChartRecreate = true;
        this.queueRenderChart();
      },
      localeReload: () => this.loadActiveTab(),
    });
    void this.loadActiveTab();
    this.pollTimer = window.setInterval(() => void this.loadActiveTab(), 60_000);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.unbindLifecycle?.();
    if (this.pollTimer) window.clearInterval(this.pollTimer);
    this.chartHandle?.destroy();
    this.chartHandle = undefined;
    this.chartHasTemp = null;
  }

  updated(changed: PropertyValues<this>): void {
    if (changed.has("navHint") && this.navHint) {
      this.applyNavHint(this.navHint);
      void this.loadActiveTab();
    }
    if (this.tab !== "timeline") {
      this.chartHandle?.destroy();
      this.chartHandle = undefined;
      return;
    }
    const c = changed as Map<string, unknown>;
    if (c.has("rows") || c.has("hours") || c.has("tab") || c.has("gridEvents")) {
      this.queueRenderChart();
    }
  }

  private applyNavHint(hint: HistoryNavHint | null): void {
    if (!hint) return;
    if (hint.view) this.tab = hint.view;
    if (hint.activity) this.activityTab = hint.activity;
    if (hint.cycleId) this.cycleFilter = hint.cycleId;
  }

  private clearCycleFilter(): void {
    this.cycleFilter = null;
    void this.loadActiveTab();
  }

  private async loadActiveTab(): Promise<void> {
    const errors: string[] = [];
    try {
      if (this.tab === "timeline") {
        await Promise.all([
          this.loadTelemetry().catch((e) => errors.push((e as Error).message)),
          this.loadGridEvents().catch((e) => errors.push((e as Error).message)),
        ]);
      } else if (this.tab === "decisions") {
        await this.loadDecisions().catch((e) => errors.push((e as Error).message));
      } else if (this.activityTab === "executions") {
        await this.loadExecutions().catch((e) => errors.push((e as Error).message));
      } else if (this.activityTab === "shed") {
        await this.loadShedExecutions().catch((e) => errors.push((e as Error).message));
      } else {
        await this.loadGridEvents().catch((e) => errors.push((e as Error).message));
      }
    } catch (e) {
      errors.push(e instanceof Error ? e.message : String(e));
    }
    this.loadError = errors[0] ?? "";
  }

  private async loadTelemetry(): Promise<void> {
    this.rows = await api.historyTelemetry(this.hours);
  }

  private async loadDecisions(): Promise<void> {
    this.decisions = await api.historyDecisions(100, this.cycleFilter ?? undefined);
  }

  private async loadGridEvents(): Promise<void> {
    const days = Math.max(1, Math.ceil(this.hours / 24));
    this.gridEvents = await api.historyGridEvents(days);
  }

  private async loadExecutions(): Promise<void> {
    const page = await api.historyExecutions(100, this.cycleFilter ?? undefined);
    // When filtering by cycle, keep every row (no consecutive dedupe).
    this.executions = this.cycleFilter ? page.items : dedupeConsecutiveExecutions(page.items);
    this.executionsCursor = page.next_cursor;
  }

  private async loadMoreExecutions(): Promise<void> {
    if (!this.executionsCursor || this.executionsLoadingMore) return;
    this.executionsLoadingMore = true;
    try {
      const page = await api.historyExecutions(100, this.cycleFilter ?? undefined, this.executionsCursor);
      const merged = [...this.executions, ...page.items];
      this.executions = this.cycleFilter ? merged : dedupeConsecutiveExecutions(merged);
      this.executionsCursor = page.next_cursor;
    } catch (e) {
      this.loadError = e instanceof Error ? e.message : String(e);
    } finally {
      this.executionsLoadingMore = false;
    }
  }

  private async loadShedExecutions(): Promise<void> {
    const page = await api.historyShedExecutions(100, this.cycleFilter ?? undefined);
    this.shedExecs = this.cycleFilter ? page.items : dedupeConsecutiveShedExecutions(page.items);
    this.shedExecsCursor = page.next_cursor;
  }

  private async loadMoreShedExecutions(): Promise<void> {
    if (!this.shedExecsCursor || this.shedExecsLoadingMore) return;
    this.shedExecsLoadingMore = true;
    try {
      const page = await api.historyShedExecutions(100, this.cycleFilter ?? undefined, this.shedExecsCursor);
      const merged = [...this.shedExecs, ...page.items];
      this.shedExecs = this.cycleFilter ? merged : dedupeConsecutiveShedExecutions(merged);
      this.shedExecsCursor = page.next_cursor;
    } catch (e) {
      this.loadError = e instanceof Error ? e.message : String(e);
    } finally {
      this.shedExecsLoadingMore = false;
    }
  }

  private onHours(e: Event): void {
    this.hours = Number((e.target as HTMLSelectElement).value);
    void this.loadActiveTab();
  }

  private setTab(t: HistoryViewTab): void {
    this.tab = t;
    this.emitNavChange();
    void this.loadActiveTab();
  }

  private setActivityTab(t: ActivityTab): void {
    this.activityTab = t;
    this.emitNavChange();
    void this.loadActiveTab();
  }

  private emitNavChange(): void {
    window.dispatchEvent(
      new CustomEvent("solar-history-nav-change", {
        detail: {
          view: this.tab,
          activity: this.tab === "activity" ? this.activityTab : undefined,
        } satisfies HistoryNavHint,
        bubbles: true,
        composed: true,
      }),
    );
  }

  private entityLabel(id: string): string {
    return entityDisplayName(id, this.entities);
  }

  private entityLabels(ids: string[]): string {
    return ids.map((id) => this.entityLabel(id)).join(", ");
  }

  private toggleDecision(ts: string): void {
    this.expandedDecisionTs = this.expandedDecisionTs === ts ? "" : ts;
  }

  private toggleActivity(key: string): void {
    this.expandedActivityKey = this.expandedActivityKey === key ? "" : key;
  }

  private onActivityRowKeydown(e: KeyboardEvent, key: string): void {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      this.toggleActivity(key);
    }
  }

  private shedExecBatches(): Array<{ ts: string; tiers: TierShedResultSummary[] }> {
    const tsOrder: string[] = [];
    const byTs = new Map<string, ShedExecutionRow[]>();
    for (const row of this.shedExecs) {
      if (!byTs.has(row.ts)) {
        tsOrder.push(row.ts);
        byTs.set(row.ts, []);
      }
      byTs.get(row.ts)!.push(row);
    }
    return tsOrder.map((ts) => ({
      ts,
      tiers: groupShedResultsByTier(byTs.get(ts)! as ShedResult[]),
    }));
  }

  private tierShedResultBadge(summary: TierShedResultSummary): ReturnType<typeof html> {
    if (summary.allVerified) {
      return html`<span class="pill good">${t("ui.decision.verified")}</span>`;
    }
    const skip =
      summary.uniformSkipReasonText ??
      summary.primarySkipReasonText ??
      summary.uniformSkipReason ??
      summary.primarySkipReason ??
      t("ui.decision.skipped");
    return html`<span class="pill muted">${skip}</span>`;
  }

  private recentEvents(): string[] {
    return this.gridEvents
      .slice(0, 5)
      .map(
        (g) =>
          `${formatDateTime(g.ts, this.dateFmt())} ${g.grid_present ? t("ui.history.gridOn") : t("ui.history.gridOff")}`,
      );
  }

  private renderChart(): void {
    if (!this.chartEl || this.tab !== "timeline") return;
    const xs = this.rows.map((r) => Math.floor(new Date(r.ts).getTime() / 1000));
    const soc = this.rows.map((r) => r.battery_soc);
    const pv = this.rows.map((r) => r.pv_power);
    const load = this.rows.map((r) => r.load_power);
    const battTemp = this.rows.map((r) => r.battery_temp);
    const outdoor = this.rows.map((r) => r.outdoor_temp);
    const hasTemp = battTemp.some((v) => v != null) || outdoor.some((v) => v != null);
    const data = (
      hasTemp ? [xs, pv, load, soc, battTemp, outdoor] : [xs, pv, load, soc]
    ) as unknown as uPlot.AlignedData;

    if (xs.length === 0) {
      this.chartHandle?.destroy();
      this.chartHandle = undefined;
      this.chartHasTemp = null;
      return;
    }

    const rangeFrom = xs[0]!;
    const rangeTo = xs[xs.length - 1]!;
    const absentBands = gridAbsentIntervals(this.gridEvents, rangeFrom, rangeTo);

    const canUpdate =
      !this.forceChartRecreate &&
      this.chartHandle?.chart != null &&
      this.chartHasTemp === hasTemp &&
      this.chartEl.contains(this.chartHandle.chart.root);

    if (canUpdate) {
      this.chartHandle!.chart!.setData(data, true);
      this.forceChartRecreate = false;
      return;
    }

    this.forceChartRecreate = false;
    this.chartHandle?.destroy();
    const good = cssVar(this.chartEl, "--good", "#2fbf71");
    const accent = cssVar(this.chartEl, "--accent", "#ffb020");
    const accent2 = cssVar(this.chartEl, "--accent-2", "#4cc2ff");
    const muted = cssVar(this.chartEl, "--muted", "#9aa4b2");
    const axisStroke = cssVar(this.chartEl, "--muted", "#9aa4b2");
    const gridStroke = cssVar(this.chartEl, "--border", "rgba(255,255,255,0.06)");
    const dateFmt = this.dateFmt();
    const series = [
      {},
      { label: t("ui.history.seriesPv"), stroke: accent, width: 1, scale: "power" },
      { label: t("ui.history.seriesLoad"), stroke: accent2, width: 1, scale: "power" },
      { label: t("ui.history.seriesSoc"), stroke: good, width: 2, scale: "%" },
      ...(hasTemp
        ? [
            { label: t("ui.history.seriesBattTemp"), stroke: muted, width: 1, scale: "temp" },
            { label: t("ui.history.seriesOutdoorTemp"), stroke: good, width: 1, scale: "temp" },
          ]
        : []),
    ];
    const axisSize = chartAxisPaddingRight(hasTemp);
    const axisGap = window.innerWidth < 400 ? 4 : 8;
    this.chartHandle = makeChart(this.chartEl, [], data, {
      showLegend: false,
      cursorLegendEl: this.cursorLegendEl,
      cursorDateFormat: dateFmt,
      axisDateFormat: dateFmt,
      padding: [8, axisSize, 14, 0],
      extraHooks: gridAbsentBandHooks(this.chartEl, absentBands),
      scales: {
        x: { time: true },
        power: {},
        "%": { range: [0, 100] },
        ...(hasTemp ? { temp: {} } : {}),
      },
      series,
      axes: [
        { stroke: axisStroke, grid: { stroke: gridStroke }, ticks: { stroke: gridStroke } },
        { scale: "power", stroke: axisStroke, grid: { stroke: gridStroke }, ticks: { stroke: gridStroke } },
        { side: 1, scale: "%", stroke: good, grid: { show: false }, ticks: { stroke: gridStroke }, size: axisSize, gap: axisGap },
        ...(hasTemp
          ? [{ scale: "temp", side: 1, stroke: muted, grid: { show: false }, ticks: { stroke: gridStroke }, size: axisSize, gap: axisGap }]
          : []),
      ],
    });
    this.chartHasTemp = hasTemp;
  }

  private skipLabel(
    row: { skipped_reason: string | null; skipped_reason_text?: string | null },
    fallback: string,
  ): string {
    return row.skipped_reason_text ?? row.skipped_reason ?? fallback;
  }

  private resultBadge(applied: boolean, verified: boolean, skip: string): ReturnType<typeof html> {
    if (applied && verified) return html`<span class="pill good">${t("ui.decision.verified")}</span>`;
    if (applied) return html`<span class="pill warn">${t("ui.decision.appliedShort")}</span>`;
    return html`<span class="pill muted">${skip}</span>`;
  }

  private renderDecisions() {
    if (!this.decisions.length) {
      return html`<p class="label">${t("ui.history.noDecisions")}</p>`;
    }
    const fmt = this.dateFmt();
    return html`
      <div class="table-scroll">
        <table class="table">
          <thead>
            <tr>
              <th>${t("ui.history.colTime")}</th><th>${t("ui.history.colTarget")}</th><th>${t("ui.history.colRisk")}</th><th>${t("ui.history.colSummary")}</th><th>${t("ui.history.colShed")}</th>
            </tr>
          </thead>
          <tbody>
            ${this.decisions.map(
              (d) => {
                const risk = formatRiskFromDecision({
                  score: d.blackout_risk_score,
                  level: d.blackout_risk,
                });
                const expanded = this.expandedDecisionTs === d.ts;
                return html`
                <tr
                  class="expandable"
                  role="button"
                  tabindex="0"
                  aria-expanded=${expanded}
                  @click=${() => this.toggleDecision(d.ts)}
                  @keydown=${(e: KeyboardEvent) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      this.toggleDecision(d.ts);
                    }
                  }}
                >
                  <td>${formatDateTime(d.ts, fmt)}</td>
                  <td>${d.target_soc.toFixed(0)}%</td>
                  <td>
                    ${risk
                      ? html`<span class="pill ${risk.pillClass}">${risk.label}${risk.pct ? html` ${risk.pct}` : null}</span>`
                      : t("ui.history.dash")}
                  </td>
                  <td>${d.summary}</td>
                  <td>${(d.shed_actions ?? []).length}</td>
                </tr>
                ${expanded
                  ? html`<tr class="expanded-row"><td colspan="5">
                      ${d.slim ? html`<div>${t("ui.history.samePlan")}</div>` : null}
                      ${d.cycle_id ? html`<div>${t("ui.history.cycleId")}: ${d.cycle_id}</div>` : null}
                      ${d.reserve_rationale ? html`<div>${d.reserve_rationale}</div>` : null}
                      ${d.grid_charge
                        ? html`<div style="margin-top:6px">${t("ui.decision.gridCharge")}: ${
                            d.grid_charge.enabled
                              ? `${d.grid_charge.target_amps} A`
                              : t("common.off")
                          }${d.grid_charge.rationale ? ` — ${d.grid_charge.rationale}` : ""}</div>`
                        : null}
                      ${(d.actions ?? []).length
                        ? html`<div style="margin-top:6px">${(d.actions ?? [])
                            .map((a) => `${a.capability}=${a.value}`)
                            .join(" · ")}</div>`
                        : null}
                      ${(d.shed_actions ?? []).length
                        ? html`<div style="margin-top:6px">${(d.shed_actions ?? []).map((a) => `${a.tier}: ${a.desired_on ? t("common.on") : t("ui.decision.shed")} (${a.reason})`).join(" · ")}</div>`
                        : null}
                      ${d.cycle_id
                        ? html`<div style="margin-top:8px">
                            <button type="button" class="link-btn" @click=${(e: Event) => {
                              e.stopPropagation();
                              this.cycleFilter = d.cycle_id ?? null;
                              this.tab = "activity";
                              this.activityTab = "executions";
                              void this.loadActiveTab();
                            }}>${t("ui.decision.relatedWrites")} →</button>
                          </div>`
                        : null}
                    </td></tr>`
                  : null}
              `;
              },
            )}
          </tbody>
        </table>
      </div>
    `;
  }

  private renderExecutions() {
    if (!this.executions.length) {
      return html`<p class="label">${t("ui.history.noExecutions")}</p>`;
    }
    const fmt = this.dateFmt();
    return html`
      <div class="table-scroll">
        <table class="table">
          <thead>
            <tr><th>${t("ui.history.colTime")}</th><th>${t("ui.history.colCapability")}</th><th>${t("ui.history.colResult")}</th></tr>
          </thead>
          <tbody>
            ${this.executions.map((e) => {
              const key = `exec:${e.ts}|${e.capability}`;
              const expanded = this.expandedActivityKey === key;
              const skip = this.skipLabel(e, t("ui.decision.skipped"));
              const detail = [
                `${t("ui.history.colRequested")}: ${e.requested}`,
                skip && !e.applied ? skip : "",
                e.error ?? "",
              ]
                .filter(Boolean)
                .join(" · ");
              return html`
                <tr
                  class="expandable"
                  role="button"
                  tabindex="0"
                  aria-expanded=${expanded}
                  aria-label=${t("ui.history.expandRow")}
                  @click=${() => this.toggleActivity(key)}
                  @keydown=${(e: KeyboardEvent) => this.onActivityRowKeydown(e, key)}
                >
                  <td>${formatDateTime(e.ts, fmt)}</td>
                  <td>${capabilityLabel(e.capability)}</td>
                  <td>${this.resultBadge(e.applied, e.verified, skip)}</td>
                </tr>
                ${expanded && detail
                  ? html`<tr class="expanded-row"><td colspan="3">${detail}</td></tr>`
                  : null}
              `;
            })}
          </tbody>
        </table>
      </div>
      ${this.executionsCursor
        ? html`<div class="load-more-row">
            <button type="button" class="link-btn" ?disabled=${this.executionsLoadingMore} @click=${() => this.loadMoreExecutions()}>
              ${this.executionsLoadingMore ? t("common.loading") : t("ui.history.loadMore")}
            </button>
          </div>`
        : null}
    `;
  }

  private renderShedExecutions() {
    if (!this.shedExecs.length) {
      return html`<p class="label">${t("ui.history.noShed")}</p>`;
    }
    const fmt = this.dateFmt();
    const batches = this.shedExecBatches();
    return html`
      <div class="table-scroll">
        <table class="table">
          <thead>
            <tr>
              <th>${t("ui.history.colTime")}</th><th>${t("ui.history.colTier")}</th><th>${t("ui.history.colDesired")}</th><th>${t("ui.history.colResult")}</th><th>${t("ui.history.colEntities")}</th>
            </tr>
          </thead>
          <tbody>
            ${batches.flatMap(({ ts, tiers }) =>
              tiers.map((summary) => {
                const key = `shed:${ts}|${summary.tier}`;
                const expanded = this.expandedActivityKey === key;
                return html`
                  <tr
                    class="expandable"
                    role="button"
                    tabindex="0"
                    title=${shedResultTooltip(summary)}
                    aria-expanded=${expanded}
                    aria-label=${t("ui.history.expandRow")}
                    @click=${() => this.toggleActivity(key)}
                    @keydown=${(e: KeyboardEvent) => this.onActivityRowKeydown(e, key)}
                  >
                    <td>${formatDateTime(ts, fmt)}</td>
                    <td>${summary.tier}</td>
                    <td>${summary.desired_on ? t("common.on") : t("common.off")}</td>
                    <td>${this.tierShedResultBadge(summary)}</td>
                    <td>${summary.entities.length}</td>
                  </tr>
                  ${expanded
                    ? html`<tr class="expanded-row"><td colspan="5">
                        ${summary.results.map((r) => {
                          const name = this.entityLabel(r.entity);
                          const status = r.verified
                            ? t("ui.decision.verified")
                            : this.skipLabel(r, t("ui.decision.skipped"));
                          const comp =
                            (r.companions_restored?.length ?? 0) > 0
                              ? t("ui.history.restored", { list: this.entityLabels(r.companions_restored!) })
                              : (r.companions_captured?.length ?? 0) > 0
                                ? t("ui.history.captured", { list: this.entityLabels(r.companions_captured!) })
                                : "";
                          return html`<div>
                            ${name}${name !== r.entity ? html` <span class="label">(${r.entity})</span>` : null}:
                            ${r.desired_on ? t("common.on") : t("common.off")} ${status}
                            ${comp ? html` · ${comp}` : null}
                          </div>`;
                        })}
                      </td></tr>`
                    : null}
                `;
              }),
            )}
          </tbody>
        </table>
      </div>
      ${this.shedExecsCursor
        ? html`<div class="load-more-row">
            <button type="button" class="link-btn" ?disabled=${this.shedExecsLoadingMore} @click=${() => this.loadMoreShedExecutions()}>
              ${this.shedExecsLoadingMore ? t("common.loading") : t("ui.history.loadMore")}
            </button>
          </div>`
        : null}
    `;
  }

  private renderGridEvents() {
    if (!this.gridEvents.length) {
      return html`<p class="label">${t("ui.history.noGrid")}</p>`;
    }
    const fmt = this.dateFmt();
    return html`
      <div class="table-scroll">
        <table class="table">
          <thead><tr><th>${t("ui.history.colTime")}</th><th>${t("ui.history.colGrid")}</th></tr></thead>
          <tbody>
            ${this.gridEvents.map(
              (e) => html`
                <tr>
                  <td>${formatDateTime(e.ts, fmt)}</td>
                  <td>${e.grid_present ? html`<span class="pill good">${t("common.on")}</span>` : html`<span class="pill bad">${t("common.off")}</span>`}</td>
                </tr>
              `,
            )}
          </tbody>
        </table>
      </div>
    `;
  }

  render() {
    const hasTemp =
      this.rows.some((r) => r.battery_temp != null) ||
      this.rows.some((r) => r.outdoor_temp != null);
    const h = chartHeight();
    const recent = this.recentEvents();

    return html`
      <div class="card chart-card">
        <div class="head">
          <h3 style="margin:0">${t("ui.history.title")}</h3>
          ${this.tab === "timeline" || this.tab === "activity"
            ? html`<label class="label">
                ${t("ui.history.window")}
                <select .value=${String(this.hours)} @change=${this.onHours}>
                  <option value="6">6h</option>
                  <option value="24">24h</option>
                  <option value="72">3d</option>
                  <option value="168">7d</option>
                </select>
              </label>`
            : null}
        </div>
        <div class="tabs" role="tablist" aria-label=${t("ui.history.title")}>
          <button type="button" role="tab" aria-selected=${this.tab === "timeline"} class=${this.tab === "timeline" ? "active" : ""} @click=${() => this.setTab("timeline")}>${t("ui.history.tabTimeline")}</button>
          <button type="button" role="tab" aria-selected=${this.tab === "decisions"} class=${this.tab === "decisions" ? "active" : ""} @click=${() => this.setTab("decisions")}>${t("ui.history.tabDecisions")}</button>
          <button type="button" role="tab" aria-selected=${this.tab === "activity"} class=${this.tab === "activity" ? "active" : ""} @click=${() => this.setTab("activity")}>${t("ui.history.tabActivity")}</button>
        </div>
        ${this.loadError ? html`<div class="load-error">${this.loadError}</div>` : null}
        ${this.cycleFilter
          ? html`<div class="cycle-filter">
              ${t("ui.history.filteredByCycle")}: <code>${this.cycleFilter}</code>
              <button type="button" class="link-btn" @click=${this.clearCycleFilter}>${t("ui.history.clearFilter")}</button>
            </div>`
          : null}
        ${this.tab === "timeline"
          ? html`
              <div class="chart-panel">
                <div class="legend">
                  <span class="swatch"><i style="background:var(--accent)"></i>${t("ui.history.legendPv")}</span>
                  <span class="swatch"><i style="background:var(--accent-2)"></i>${t("ui.history.legendLoad")}</span>
                  <span class="swatch"><i style="background:var(--good)"></i>${t("ui.history.legendSoc")}</span>
                  <span class="swatch"><i style="background:color-mix(in srgb, var(--bad) 40%, transparent)"></i>${t("ui.history.legendGridOutage")}</span>
                  ${hasTemp
                    ? html`
                        <span class="swatch"><i style="background:var(--muted)"></i>${t("ui.history.legendBattTemp")}</span>
                        <span class="swatch"><i style="background:var(--good);opacity:0.65"></i>${t("ui.history.legendOutdoorTemp")}</span>
                      `
                    : null}
                </div>
                <div class="cursor-values"></div>
                <div class="chart-wrap" style="--chart-height:${h}px">
                  <div class="chart-mount"></div>
                </div>
              </div>
              ${this.rows.length === 0 ? html`<p class="label">${t("ui.history.noTelemetry")}</p>` : null}
              ${recent.length
                ? html`<div class="recent-strip"><span class="label">${t("ui.history.recentEvents")}:</span>${recent.map((ev) => html`<span class="ev">${ev}</span>`)}</div>`
                : null}
            `
          : this.tab === "decisions"
            ? this.renderDecisions()
            : html`
                <div class="activity-seg" role="tablist" aria-label=${t("ui.history.tabActivity")}>
                  <button type="button" role="tab" aria-selected=${this.activityTab === "executions"} class=${this.activityTab === "executions" ? "active" : ""} @click=${() => this.setActivityTab("executions")}>${t("ui.history.activityExecutions")}</button>
                  <button type="button" role="tab" aria-selected=${this.activityTab === "shed"} class=${this.activityTab === "shed" ? "active" : ""} @click=${() => this.setActivityTab("shed")}>${t("ui.history.activityShed")}</button>
                  <button type="button" role="tab" aria-selected=${this.activityTab === "grid"} class=${this.activityTab === "grid" ? "active" : ""} @click=${() => this.setActivityTab("grid")}>${t("ui.history.activityGrid")}</button>
                </div>
                ${this.activityTab === "executions"
                  ? this.renderExecutions()
                  : this.activityTab === "shed"
                    ? this.renderShedExecutions()
                    : this.renderGridEvents()}
              `}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-history-view": HistoryView;
  }
}
