import { LitElement, css, html, type PropertyValues } from "lit";
import { customElement, property, query } from "lit/decorators.js";
import type uPlot from "uplot";

import {
  chartContainerStyles,
  chartHeight,
  cssVar,
  makeChart,
  scheduleChartRender,
  type ChartHandle,
  type SeriesDef,
} from "../charts.js";
import { sharedStyles } from "../styles.js";
import type { ForecastBundle } from "../types.js";

@customElement("solar-forecast-chart")
export class ForecastChart extends LitElement {
  static styles = [
    sharedStyles,
    chartContainerStyles,
    css`
      .head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 10px; }
      .totals { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
      .totals .v { font-weight: 700; font-size: 1.05rem; font-variant-numeric: tabular-nums; }
      .legend { display: flex; gap: 14px; flex-wrap: wrap; }
      .swatch { display: inline-flex; align-items: center; gap: 6px; font-size: 0.78rem; color: var(--muted); }
      .swatch i { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
      .cursor-values { min-height: 1.2em; font-size: 0.78rem; color: var(--muted); margin-bottom: 6px; font-variant-numeric: tabular-nums; flex-shrink: 0; }
    `,
  ];

  @property({ attribute: false }) forecast: ForecastBundle | null = null;
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

  connectedCallback(): void {
    super.connectedCallback();
    window.addEventListener("solar-theme-change", this.onTheme);
  }

  updated(changed: PropertyValues<this>): void {
    if (changed.has("forecast")) {
      this.queueRenderChart();
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    window.removeEventListener("solar-theme-change", this.onTheme);
    this.chartHandle?.destroy();
    this.chartHandle = undefined;
    this.chartHasTemp = null;
  }

  private renderChart(): void {
    if (!this.chartEl || !this.forecast) return;
    const f = this.forecast;
    const tset = new Set<number>();
    const solarMap = new Map<number, number>();
    const loadMap = new Map<number, number>();
    for (const p of f.solar) {
      const t = Math.floor(new Date(p.ts).getTime() / 1000);
      solarMap.set(t, p.pv_power_w);
      tset.add(t);
    }
    for (const p of f.load) {
      const t = Math.floor(new Date(p.ts).getTime() / 1000);
      loadMap.set(t, p.load_power_w);
      tset.add(t);
    }
    const tempMap = new Map<number, number>();
    for (const p of f.temperature ?? []) {
      const t = Math.floor(new Date(p.ts).getTime() / 1000);
      tempMap.set(t, p.temp_c);
      tset.add(t);
    }
    const hasTemp = tempMap.size > 0;
    const xs = [...tset].sort((a, b) => a - b);
    const solar = xs.map((t) => solarMap.get(t) ?? null);
    const load = xs.map((t) => loadMap.get(t) ?? null);
    const temp = xs.map((t) => tempMap.get(t) ?? null);
    const data = (
      hasTemp ? [xs, solar, load, temp] : [xs, solar, load]
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

    const accent = cssVar(this.chartEl, "--accent", "#ffb020");
    const accent2 = cssVar(this.chartEl, "--accent-2", "#4cc2ff");
    const muted = cssVar(this.chartEl, "--muted", "#9aa4b2");
    const series: SeriesDef[] = [
      { label: "Solar (W)", stroke: accent, fill: "rgba(255,176,32,0.12)" },
      { label: "Load (W)", stroke: accent2, fill: "rgba(76,194,255,0.10)" },
    ];
    const axisStroke = cssVar(this.chartEl, "--muted", "#9aa4b2");
    const gridStroke = cssVar(this.chartEl, "--border", "rgba(255,255,255,0.06)");
    const opts: Partial<uPlot.Options> = { padding: [8, hasTemp ? 56 : 16, 14, 0] };
    if (hasTemp) {
      series.push({ label: "Temp (\u00b0C)", stroke: muted, dash: [4, 3], scale: "temp" });
      opts.scales = { x: { time: true }, temp: {} };
      opts.axes = [
        { stroke: axisStroke, grid: { stroke: gridStroke }, ticks: { stroke: gridStroke } },
        { stroke: axisStroke, grid: { stroke: gridStroke }, ticks: { stroke: gridStroke } },
        {
          scale: "temp",
          side: 1,
          stroke: axisStroke,
          grid: { show: false },
          ticks: { stroke: gridStroke },
          size: 50,
        },
      ];
    }
    this.chartHandle = makeChart(this.chartEl, series, data, {
      ...opts,
      showLegend: false,
      cursorLegendEl: this.cursorLegendEl,
    });
    this.chartHasTemp = hasTemp;
  }

  render() {
    const f = this.forecast;
    const h = chartHeight();
    return html`
      <div class="card chart-card">
        <div class="head">
          <h3 style="margin:0">Forecast &amp; plan (48h)</h3>
          <div class="totals">
            <div class="legend">
              <span class="swatch"><i style="background:var(--accent)"></i>Solar</span>
              <span class="swatch"><i style="background:var(--accent-2)"></i>Load</span>
              ${f && f.temperature && f.temperature.length > 0
                ? html`<span class="swatch"><i style="background:var(--muted)"></i>Temp</span>`
                : null}
            </div>
            <div><span class="label">Today</span> <span class="v">${f ? f.solar_today_kwh.toFixed(1) : "--"} kWh</span></div>
            <div><span class="label">Tomorrow</span> <span class="v">${f ? f.solar_tomorrow_kwh.toFixed(1) : "--"} kWh</span></div>
            ${f && (f.heating_degree_hours_24h > 0 || f.cooling_degree_hours_24h > 0)
              ? html`<div><span class="label">Degree-hrs 24h</span> <span class="v">${f.heating_degree_hours_24h.toFixed(0)}H / ${f.cooling_degree_hours_24h.toFixed(0)}C</span></div>`
              : null}
            ${f?.cloudy_tomorrow ? html`<span class="pill warn">Cloudy tomorrow</span>` : null}
            ${f?.degraded
              ? html`<span class="pill warn" title=${(f.degraded_reasons ?? []).join("; ")}>Degraded forecast</span>`
              : null}
          </div>
        </div>
        <div class="chart-panel">
          <div class="cursor-values"></div>
          <div class="chart-wrap" style="--chart-height:${h}px">
            <div class="chart-mount"></div>
          </div>
        </div>
        ${!f || f.solar.length === 0
          ? html`<p class="label">No forecast yet. Set your latitude/longitude and panels in the Settings tab.</p>`
          : null}
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "solar-forecast-chart": ForecastChart;
  }
}
