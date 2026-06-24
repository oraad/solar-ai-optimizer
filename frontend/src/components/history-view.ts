import { LitElement, css, html, type PropertyValues } from "lit";
import { customElement, query, state } from "lit/decorators.js";
import type uPlot from "uplot";

import { api } from "../api.js";
import {
  chartContainerStyles,
  chartHeight,
  cssVar,
  makeChart,
  scheduleChartRender,
  type ChartHandle,
} from "../charts.js";
import { sharedStyles } from "../styles.js";
import type {
  DecisionHistoryRow,
  ExecutionHistoryRow,
  GridEventRow,
  ShedExecutionRow,
  Telemetry,
} from "../types.js";

type HistoryTab = "chart" | "decisions" | "grid" | "executions" | "shed";

@customElement("solar-history-view")
export class HistoryView extends LitElement {
  static styles = [
    sharedStyles,
    chartContainerStyles,
    css`
      .head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
      .tabs { display: flex; gap: 6px; margin-bottom: 12px; }
      .tabs button { padding: 6px 12px; border-radius: 6px; border: 1px solid var(--border); background: var(--panel-2); cursor: pointer; }
      .tabs button.active { border-color: var(--accent); color: var(--accent); }
      .legend { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 8px; flex-shrink: 0; }
      .swatch { display: inline-flex; align-items: center; gap: 6px; font-size: 0.78rem; color: var(--muted); }
      .swatch i { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
      .cursor-values { min-height: 1.2em; font-size: 0.78rem; color: var(--muted); margin-bottom: 6px; font-variant-numeric: tabular-nums; flex-shrink: 0; }
      select { margin-left: 8px; }
      .table { width: 100%; border-collapse: collapse; font-size: 0.82rem; }
      .table th, .table td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); }
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
  private pollTimer?: number;

  connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("solar-theme-change", this.onTheme);
    void this.loadAll();
    this.pollTimer = window.setInterval(() => void this.loadAll(), 60_000);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    window.removeEventListener("solar-theme-change", this.onTheme);
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
      { label: "PV (W)", stroke: accent, width: 1, scale: "power" },
      { label: "Load (W)", stroke: accent2, width: 1, scale: "power" },
      { label: "SOC (%)", stroke: good, width: 2, scale: "%" },
      ...(hasTemp
        ? [
            { label: "Batt °C", stroke: muted, width: 1, scale: "temp" },
            { label: "Outdoor °C", stroke: good, width: 1, scale: "temp" },
          ]
        : []),
    ];
    this.chartHandle = makeChart(
      this.chartEl,
      [],
      data,
      {
        showLegend: false,
        cursorLegendEl: this.cursorLegendEl,
        padding: [8, hasTemp ? 72 : 56, 14, 0],
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
            size: 56,
            gap: 8,
          },
          ...(hasTemp
            ? [
                {
                  scale: "temp",
                  side: 1,
                  stroke: muted,
                  grid: { show: false },
                  ticks: { stroke: gridStroke },
                  size: 60,
                  gap: 8,
                },
              ]
            : []),
        ],
      },
    );
    this.chartHasTemp = hasTemp;
  }

  private renderDecisions() {
    if (!this.decisions.length) {
      return html`<p class="label">No decisions recorded yet.</p>`;
    }
    return html`
      <div class="scroll">
        <table class="table">
          <thead>
            <tr>
              <th>Time</th><th>Target</th><th>Risk</th><th>Summary</th><th>Shed</th>
            </tr>
          </thead>
          <tbody>
            ${this.decisions.map(
              (d) => html`
                <tr title=${d.reserve_rationale || ""}>
                  <td>${new Date(d.ts).toLocaleString()}</td>
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
      return html`<p class="label">No inverter writes recorded yet.</p>`;
    }
    return html`
      <div class="scroll">
        <table class="table">
          <thead>
            <tr><th>Time</th><th>Capability</th><th>Requested</th><th>Result</th></tr>
          </thead>
          <tbody>
            ${this.executions.map(
              (e) => html`
                <tr title=${e.skipped_reason || e.error || ""}>
                  <td>${new Date(e.ts).toLocaleString()}</td>
                  <td>${e.capability}</td>
                  <td>${e.requested}</td>
                  <td>
                    ${e.applied
                      ? e.verified
                        ? "verified"
                        : "applied"
                      : e.skipped_reason || e.error || "skipped"}
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
      return html`<p class="label">No shed switch writes recorded yet.</p>`;
    }
    return html`
      <div class="scroll">
        <table class="table">
          <thead>
            <tr><th>Time</th><th>Tier</th><th>Entity</th><th>Desired</th><th>Result</th><th>Companions</th></tr>
          </thead>
          <tbody>
            ${this.shedExecs.map(
              (e) => {
                const comp =
                  (e.companions_restored?.length ?? 0) > 0
                    ? `restored: ${e.companions_restored!.join(", ")}`
                    : (e.companions_captured?.length ?? 0) > 0
                      ? `captured: ${e.companions_captured!.join(", ")}`
                      : "";
                const title = [e.skipped_reason, e.error, comp].filter(Boolean).join(" · ");
                return html`
                <tr title=${title}>
                  <td>${new Date(e.ts).toLocaleString()}</td>
                  <td>${e.tier}</td>
                  <td>${e.entity}</td>
                  <td>${e.desired_on ? "ON" : "OFF"}</td>
                  <td>
                    ${e.applied
                      ? e.verified
                        ? "ok"
                        : "applied"
                      : e.skipped_reason || "skipped"}
                  </td>
                  <td>${comp || "—"}</td>
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
      return html`<p class="label">No grid transitions in this window.</p>`;
    }
    return html`
      <div class="scroll">
        <table class="table">
          <thead><tr><th>Time</th><th>Grid</th></tr></thead>
          <tbody>
            ${this.gridEvents.map(
              (e) => html`
                <tr>
                  <td>${new Date(e.ts).toLocaleString()}</td>
                  <td>${e.grid_present ? "ON" : "OFF"}</td>
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
          <h3 style="margin:0">History</h3>
          <label class="label">
            Window
            <select .value=${String(this.hours)} @change=${this.onHours}>
              <option value="6">6h</option>
              <option value="24">24h</option>
              <option value="72">3d</option>
              <option value="168">7d</option>
            </select>
          </label>
        </div>
        <div class="tabs">
          <button class=${this.tab === "chart" ? "active" : ""} @click=${() => this.setTab("chart")}>Chart</button>
          <button class=${this.tab === "decisions" ? "active" : ""} @click=${() => this.setTab("decisions")}>Decisions</button>
          <button class=${this.tab === "grid" ? "active" : ""} @click=${() => this.setTab("grid")}>Grid events</button>
          <button class=${this.tab === "executions" ? "active" : ""} @click=${() => this.setTab("executions")}>Writes</button>
          <button class=${this.tab === "shed" ? "active" : ""} @click=${() => this.setTab("shed")}>Shed writes</button>
        </div>
        ${this.loadError
          ? html`<div class="load-error">${this.loadError}</div>`
          : null}
        ${this.tab === "chart"
          ? html`
              <div class="chart-panel">
                <div class="legend">
                  <span class="swatch"><i style="background:var(--accent)"></i>PV</span>
                  <span class="swatch"><i style="background:var(--accent-2)"></i>Load</span>
                  <span class="swatch"><i style="background:var(--good)"></i>SOC</span>
                  ${hasTemp
                    ? html`
                        <span class="swatch"><i style="background:var(--muted)"></i>Batt °C</span>
                        <span class="swatch"><i style="background:var(--good);opacity:0.65"></i>Outdoor °C</span>
                      `
                    : null}
                </div>
                <div class="cursor-values"></div>
                <div class="chart-wrap" style="--chart-height:${h}px">
                  <div class="chart-mount"></div>
                </div>
              </div>
              ${this.rows.length === 0
                ? html`<p class="label">No telemetry yet.</p>`
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
