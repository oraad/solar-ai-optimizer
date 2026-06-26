import { LitElement, css, html, type PropertyValues } from "lit";
import { customElement, property, query, state } from "lit/decorators.js";
import type uPlot from "uplot";

import { api } from "../api.js";
import {
  chartContainerStyles,
  chartAxisPaddingRight,
  chartHeight,
  cssVar,
  makeChart,
  scheduleChartRender,
  type ChartHandle,
} from "../charts.js";
import { formatDateTime } from "../date-format.js";
import { entityDisplayName } from "../entity-resolve.js";
import { t } from "../i18n.js";
import { LocaleController } from "../locale-controller.js";
import { sharedStyles } from "../styles.js";
import type {
  DecisionHistoryRow,
  EntityInfo,
  ExecutionHistoryRow,
  GridEventRow,
  ShedExecutionRow,
  Telemetry,
} from "../types.js";

type HistoryTab = "chart" | "decisions" | "grid" | "executions" | "shed";

const HISTORY_DATE_FMT = "iso" as const;

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
        scroll-snap-type: x proximity;
      }
      .tabs button {
        padding: 6px 12px;
        border-radius: 6px;
        border: 1px solid var(--border);
        background: var(--panel-2);
        cursor: pointer;
        flex-shrink: 0;
        scroll-snap-align: start;
        white-space: nowrap;
      }
      @media (max-width: 760px) {
        .tabs button { min-height: 44px; padding: 8px 14px; }
      }
      .tabs button.active { border-color: var(--accent); color: var(--accent); }
      .legend { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 8px; flex-shrink: 0; }
      .swatch { display: inline-flex; align-items: center; gap: 6px; font-size: 0.78rem; color: var(--muted); }
      .swatch i { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
      .cursor-values { min-height: 1.2em; font-size: 0.78rem; color: var(--muted); margin-bottom: 6px; font-variant-numeric: tabular-nums; flex-shrink: 0; }
      select { margin-inline-start: 8px; }
      .table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
      .table { width: 100%; border-collapse: collapse; font-size: 0.82rem; min-width: 480px; }
      .table th, .table td { text-align: start; padding: 6px 8px; border-bottom: 1px solid var(--border); }
      .table tr:hover { background: var(--panel-2); }
      .scroll { max-height: 320px; overflow: auto; }
      .load-error {
        padding: 10px 12px;
        border-radius: var(--radius-sm);
        margin-bottom: 12px;
        font-size: 0.82rem;
        border: 1px solid var(--border);
        background: color-mix(in srgb, var(--bad) 12%, var(--panel-2));
        color: var(--bad);
      }
    `,
  ];

  @state() private hours = 24;
  @state() private tab: HistoryTab = "chart";
  @state() private rows: Telemetry[] = [];
  @state() private decisions: DecisionHistoryRow[] = [];
  @state() private gridEvents: GridEventRow[] = [];
  @state() private executions: ExecutionHistoryRow[] = [];
  @state() private shedExecs: ShedExecutionRow[] = [];
  @state() private loadError = "";
  @property({ attribute: false }) entities: EntityInfo[] = [];
  @query(".chart-mount") private chartEl!: HTMLDivElement;
  @query(".cursor-values") private cursorLegendEl!: HTMLDivElement;
  private chartHandle?: ChartHandle;
  private chartHasTemp: boolean | null = null;
  private forceChartRecreate = false;
  private chartRenderLock = false;

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

  private onTheme = () => {
    this.forceChartRecreate = true;
    this.queueRenderChart();
  };
  private onDateFormat = () => {
    this.forceChartRecreate = true;
    this.queueRenderChart();
    this.requestUpdate();
  };
  private onLocale = () => {
    this.forceChartRecreate = true;
    this.queueRenderChart();
    this.requestUpdate();
    void this.loadAll();
  };
  private pollTimer?: number;

  connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("solar-theme-change", this.onTheme);
    window.addEventListener("solar-date-format-change", this.onDateFormat);
    window.addEventListener("solar-site-timezone-change", this.onDateFormat);
    window.addEventListener("solar-locale-change", this.onLocale);
    void this.loadAll();
    this.pollTimer = window.setInterval(() => void this.loadAll(), 60_000);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    window.removeEventListener("solar-theme-change", this.onTheme);
    window.removeEventListener("solar-date-format-change", this.onDateFormat);
    window.removeEventListener("solar-site-timezone-change", this.onDateFormat);
    window.removeEventListener("solar-locale-change", this.onLocale);
    if (this.pollTimer) window.clearInterval(this.pollTimer);
    this.chartHandle?.destroy();
    this.chartHandle = undefined;
    this.chartHasTemp = null;
  }

  private async loadAll(): Promise<void> {
    const errors: string[] = [];
    const tasks = [
      this.loadTelemetry().catch((e) => errors.push((e as Error).message)),
      this.loadDecisions().catch((e) => errors.push((e as Error).message)),
      this.loadGridEvents().catch((e) => errors.push((e as Error).message)),
      this.loadExecutions().catch((e) => errors.push((e as Error).message)),
      this.loadShedExecutions().catch((e) => errors.push((e as Error).message)),
    ];
    await Promise.all(tasks);
    this.loadError = errors[0] ?? "";
  }

  private async loadTelemetry(): Promise<void> {
    this.rows = await api.historyTelemetry(this.hours);
  }

  private async loadDecisions(): Promise<void> {
    this.decisions = await api.historyDecisions(100);
  }

  private async loadGridEvents(): Promise<void> {
    const days = Math.max(1, Math.ceil(this.hours / 24));
    this.gridEvents = await api.historyGridEvents(days);
  }

  private async loadExecutions(): Promise<void> {
    this.executions = await api.historyExecutions(100);
  }

  private async loadShedExecutions(): Promise<void> {
    this.shedExecs = await api.historyShedExecutions(100);
  }

  private onHours(e: Event): void {
    this.hours = Number((e.target as HTMLSelectElement).value);
    void this.loadAll();
  }

  private setTab(t: HistoryTab): void {
    this.tab = t;
  }

  private entityLabel(id: string): string {
    return entityDisplayName(id, this.entities);
  }

  private entityLabels(ids: string[]): string {
    return ids.map((id) => this.entityLabel(id)).join(", ");
  }

  updated(changed: PropertyValues<this>): void {
    if (this.tab !== "chart") {
      this.chartHandle?.destroy();
      this.chartHandle = undefined;
      return;
    }
    const c = changed as Map<string, unknown>;
    if (c.has("rows") || c.has("hours") || c.has("tab")) {
      this.queueRenderChart();
    }
  }

  private renderChart(): void {
    if (!this.chartEl || this.tab !== "chart") return;
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
    this.chartHandle = makeChart(
      this.chartEl,
      [],
      data,
      {
        showLegend: false,
        cursorLegendEl: this.cursorLegendEl,
        cursorDateFormat: HISTORY_DATE_FMT,
        axisDateFormat: HISTORY_DATE_FMT,
        padding: [8, axisSize, 14, 0],
        scales: {
          x: { time: true },
          power: {},
          "%": { range: [0, 100] },
          ...(hasTemp ? { temp: {} } : {}),
        },
        series,
        axes: [
          { stroke: axisStroke, grid: { stroke: gridStroke }, ticks: { stroke: gridStroke } },
          {
            scale: "power",
            stroke: axisStroke,
            grid: { stroke: gridStroke },
            ticks: { stroke: gridStroke },
          },
          {
            side: 1,
            scale: "%",
            stroke: good,
            grid: { show: false },
            ticks: { stroke: gridStroke },
            size: axisSize,
            gap: axisGap,
          },
          ...(hasTemp
            ? [
                {
                  scale: "temp",
                  side: 1,
                  stroke: muted,
                  grid: { show: false },
                  ticks: { stroke: gridStroke },
                  size: axisSize,
                  gap: axisGap,
                },
              ]
            : []),
        ],
      },
    );
    this.chartHasTemp = hasTemp;
  }

  private skipLabel(
    row: { skipped_reason: string | null; skipped_reason_text?: string | null },
    fallback: string,
  ): string {
    return row.skipped_reason_text ?? row.skipped_reason ?? fallback;
  }

  private renderDecisions() {
    if (!this.decisions.length) {
      return html`<p class="label">${t("ui.history.noDecisions")}</p>`;
    }
    return html`
      <div class="scroll table-scroll">
        <table class="table">
          <thead>
            <tr>
              <th>${t("ui.history.colTime")}</th><th>${t("ui.history.colTarget")}</th><th>${t("ui.history.colRisk")}</th><th>${t("ui.history.colSummary")}</th><th>${t("ui.history.colShed")}</th>
            </tr>
          </thead>
          <tbody>
            ${this.decisions.map(
              (d) => html`
                <tr title=${d.reserve_rationale || ""}>
                  <td>${formatDateTime(d.ts, HISTORY_DATE_FMT)}</td>
                  <td>${d.target_soc.toFixed(0)}%</td>
                  <td>${d.blackout_risk}</td>
                  <td>${d.summary}</td>
                  <td>${(d.shed_actions ?? []).length}</td>
                </tr>
              `,
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
    return html`
      <div class="scroll table-scroll">
        <table class="table">
          <thead>
            <tr><th>${t("ui.history.colTime")}</th><th>${t("ui.history.colCapability")}</th><th>${t("ui.history.colRequested")}</th><th>${t("ui.history.colResult")}</th></tr>
          </thead>
          <tbody>
            ${this.executions.map(
              (e) => html`
                <tr title=${this.skipLabel(e, "") || e.error || ""}>
                  <td>${formatDateTime(e.ts, HISTORY_DATE_FMT)}</td>
                  <td>${e.capability}</td>
                  <td>${e.requested}</td>
                  <td>
                    ${e.applied
                      ? e.verified
                        ? t("ui.decision.verified")
                        : t("ui.decision.appliedShort")
                      : this.skipLabel(e, t("ui.decision.skipped")) || e.error || t("ui.decision.skipped")}
                  </td>
                </tr>
              `,
            )}
          </tbody>
        </table>
      </div>
    `;
  }

  private renderShedExecutions() {
    if (!this.shedExecs.length) {
      return html`<p class="label">${t("ui.history.noShed")}</p>`;
    }
    return html`
      <div class="scroll table-scroll">
        <table class="table">
          <thead>
            <tr><th>${t("ui.history.colTime")}</th><th>${t("ui.history.colTier")}</th><th>${t("ui.history.colEntity")}</th><th>${t("ui.history.colDesired")}</th><th>${t("ui.history.colResult")}</th><th>${t("ui.history.colCompanions")}</th></tr>
          </thead>
          <tbody>
            ${this.shedExecs.map(
              (e) => {
                const entityName = this.entityLabel(e.entity);
                const comp =
                  (e.companions_restored?.length ?? 0) > 0
                    ? t("ui.history.restored", { list: this.entityLabels(e.companions_restored!) })
                    : (e.companions_captured?.length ?? 0) > 0
                      ? t("ui.history.captured", { list: this.entityLabels(e.companions_captured!) })
                      : "";
                const titleParts = [this.skipLabel(e, ""), e.error, comp];
                if (entityName !== e.entity) titleParts.push(e.entity);
                const title = titleParts.filter(Boolean).join(" · ");
                return html`
                <tr title=${title}>
                  <td>${formatDateTime(e.ts, HISTORY_DATE_FMT)}</td>
                  <td>${e.tier}</td>
                  <td>${entityName}</td>
                  <td>${e.desired_on ? t("common.on") : t("common.off")}</td>
                  <td>
                    ${e.applied
                      ? e.verified
                        ? t("ui.decision.ok")
                        : t("ui.decision.appliedShort")
                      : this.skipLabel(e, t("ui.decision.skipped"))}
                  </td>
                  <td>${comp || t("ui.history.dash")}</td>
                </tr>
              `;
              },
            )}
          </tbody>
        </table>
      </div>
    `;
  }

  private renderGridEvents() {
    if (!this.gridEvents.length) {
      return html`<p class="label">${t("ui.history.noGrid")}</p>`;
    }
    return html`
      <div class="scroll table-scroll">
        <table class="table">
          <thead><tr><th>${t("ui.history.colTime")}</th><th>${t("ui.history.colGrid")}</th></tr></thead>
          <tbody>
            ${this.gridEvents.map(
              (e) => html`
                <tr>
                  <td>${formatDateTime(e.ts, HISTORY_DATE_FMT)}</td>
                  <td>${e.grid_present ? t("common.on") : t("common.off")}</td>
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
    return html`
      <div class="card chart-card">
        <div class="head">
          <h3 style="margin:0">${t("ui.history.title")}</h3>
          <label class="label">
            ${t("ui.history.window")}
            <select .value=${String(this.hours)} @change=${this.onHours}>
              <option value="6">6h</option>
              <option value="24">24h</option>
              <option value="72">3d</option>
              <option value="168">7d</option>
            </select>
          </label>
        </div>
        <div class="tabs">
          <button class=${this.tab === "chart" ? "active" : ""} @click=${() => this.setTab("chart")}>${t("ui.history.tabChart")}</button>
          <button class=${this.tab === "decisions" ? "active" : ""} @click=${() => this.setTab("decisions")}>${t("ui.history.tabDecisions")}</button>
          <button class=${this.tab === "grid" ? "active" : ""} @click=${() => this.setTab("grid")}>${t("ui.history.tabGrid")}</button>
          <button class=${this.tab === "executions" ? "active" : ""} @click=${() => this.setTab("executions")}>${t("ui.history.tabExecutions")}</button>
          <button class=${this.tab === "shed" ? "active" : ""} @click=${() => this.setTab("shed")}>${t("ui.history.tabShed")}</button>
        </div>
        ${this.loadError
          ? html`<div class="load-error">${this.loadError}</div>`
          : null}
        ${this.tab === "chart"
          ? html`
              <div class="chart-panel">
                <div class="legend">
                  <span class="swatch"><i style="background:var(--accent)"></i>${t("ui.history.legendPv")}</span>
                  <span class="swatch"><i style="background:var(--accent-2)"></i>${t("ui.history.legendLoad")}</span>
                  <span class="swatch"><i style="background:var(--good)"></i>${t("ui.history.legendSoc")}</span>
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
              ${this.rows.length === 0
                ? html`<p class="label">${t("ui.history.noTelemetry")}</p>`
                : null}
            `
          : this.tab === "decisions"
            ? this.renderDecisions()
            : this.tab === "grid"
              ? this.renderGridEvents()
              : this.tab === "executions"
                ? this.renderExecutions()
                : this.renderShedExecutions()}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-history-view": HistoryView;
  }
}
