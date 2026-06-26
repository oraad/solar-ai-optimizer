import { LitElement, css, html, type PropertyValues } from "lit";
import { customElement, property, query, state } from "lit/decorators.js";
import type uPlot from "uplot";

import { api } from "../api.js";
import { bindChartLifecycle } from "../chart-lifecycle.js";
import {
  chartContainerStyles,
  chartHeight,
  cssVar,
  makeChart,
  nowMarkerHooks,
  scheduleChartRender,
  type ChartHandle,
  type SeriesDef,
} from "../charts.js";
import { getDateFormat } from "../date-format.js";
import { t } from "../i18n.js";
import { LocaleController } from "../locale-controller.js";
import { sharedStyles } from "../styles.js";
import { runWithToast } from "../toast.js";
import type { ForecastBundle } from "../types.js";

@customElement("solar-forecast-chart")
export class ForecastChart extends LitElement {
  constructor() {
    super();
    new LocaleController(this);
  }

  static styles = [
    sharedStyles,
    chartContainerStyles,
    css`
      .head {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 12px;
        flex-wrap: wrap;
        gap: 10px;
      }
      .head-actions {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
      }
      .metrics {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
        gap: 10px;
        margin-bottom: 12px;
      }
      .metric-card {
        background: var(--panel-2);
        border: 1px solid var(--border);
        border-radius: var(--radius-sm);
        padding: 10px 12px;
      }
      .metric-card .v {
        font-weight: 700;
        font-size: 1.1rem;
        font-variant-numeric: tabular-nums;
        margin-top: 4px;
      }
      .legend { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 8px; }
      .swatch { display: inline-flex; align-items: center; gap: 6px; font-size: 0.78rem; color: var(--muted); }
      .swatch i { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
      .cursor-values { min-height: 1.2em; font-size: 0.78rem; color: var(--muted); margin-bottom: 6px; font-variant-numeric: tabular-nums; flex-shrink: 0; }
      .alert-strip {
        margin-top: 12px;
        padding: 10px 12px;
        border-radius: var(--radius-sm);
        border: 1px solid var(--border);
        background: color-mix(in srgb, var(--warn) 10%, var(--panel-2));
        font-size: 0.82rem;
        display: flex;
        flex-wrap: wrap;
        gap: 8px 12px;
        align-items: center;
      }
      .empty-cta { margin-top: 8px; }
      .updated { font-size: 0.72rem; color: var(--muted); }
    `,
  ];

  @property({ attribute: false }) forecast: ForecastBundle | null = null;
  @property({ type: String }) role: "admin" | "viewer" = "admin";
  @property({ type: Number }) forecastLastUpdate = 0;
  @property({ type: Number }) now = Date.now();
  @state() private refreshing = false;
  @query(".chart-mount") private chartEl!: HTMLDivElement;
  @query(".cursor-values") private cursorLegendEl!: HTMLDivElement;
  private chartHandle?: ChartHandle;
  private chartHasTemp: boolean | null = null;
  private forceChartRecreate = false;
  private chartRenderLock = false;
  private unbindLifecycle?: () => void;

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
    this.unbindLifecycle = bindChartLifecycle(this, {
      onThemeChange: () => {
        this.forceChartRecreate = true;
        this.queueRenderChart();
      },
      onDateFormatChange: () => {
        this.forceChartRecreate = true;
        this.queueRenderChart();
      },
      onLocaleChange: () => {
        this.forceChartRecreate = true;
        this.queueRenderChart();
      },
    });
  }

  updated(changed: PropertyValues<this>): void {
    if (changed.has("forecast")) {
      this.queueRenderChart();
    }
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    this.unbindLifecycle?.();
    this.chartHandle?.destroy();
    this.chartHandle = undefined;
    this.chartHasTemp = null;
  }

  private freshnessLabel(): string {
    if (!this.forecastLastUpdate) return "";
    const s = Math.max(0, Math.round((this.now - this.forecastLastUpdate) / 1000));
    if (s < 5) return t("ui.app.live");
    if (s < 60) return t("ui.app.updatedSeconds", { s: String(s) });
    return t("ui.app.updatedMinutes", { m: String(Math.floor(s / 60)) });
  }

  private openSettings = (): void => {
    window.dispatchEvent(
      new CustomEvent("solar-navigate-tab", { detail: "settings", bubbles: true, composed: true }),
    );
  };

  private refresh = async (): Promise<void> => {
    if (this.role !== "admin" || this.refreshing) return;
    this.refreshing = true;
    const ok = await runWithToast(
      async () => {
        const bundle = await api.refreshForecast();
        window.dispatchEvent(
          new CustomEvent("solar-forecast-refresh", { detail: bundle, bubbles: true }),
        );
        window.dispatchEvent(new Event("solar-plan-refresh"));
      },
      { loading: t("ui.overrides.toastForecastLoading"), success: t("ui.overrides.toastForecastSuccess") },
    );
    this.refreshing = false;
    if (!ok) this.requestUpdate();
  };

  private renderChart(): void {
    if (!this.chartEl || !this.forecast) return;
    const f = this.forecast;
    const tset = new Set<number>();
    const solarMap = new Map<number, number>();
    const loadMap = new Map<number, number>();
    for (const p of f.solar) {
      const ts = Math.floor(new Date(p.ts).getTime() / 1000);
      solarMap.set(ts, p.pv_power_w);
      tset.add(ts);
    }
    for (const p of f.load) {
      const ts = Math.floor(new Date(p.ts).getTime() / 1000);
      loadMap.set(ts, p.load_power_w);
      tset.add(ts);
    }
    const tempMap = new Map<number, number>();
    for (const p of f.temperature ?? []) {
      const ts = Math.floor(new Date(p.ts).getTime() / 1000);
      tempMap.set(ts, p.temp_c);
      tset.add(ts);
    }
    const hasTemp = tempMap.size > 0;
    const xs = [...tset].sort((a, b) => a - b);
    const solar = xs.map((ts) => solarMap.get(ts) ?? null);
    const load = xs.map((ts) => loadMap.get(ts) ?? null);
    const temp = xs.map((ts) => tempMap.get(ts) ?? null);
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
      { label: t("ui.forecast.seriesSolar"), stroke: accent, fill: "rgba(255,176,32,0.12)" },
      { label: t("ui.forecast.seriesLoad"), stroke: accent2, fill: "rgba(76,194,255,0.10)" },
    ];
    const axisStroke = cssVar(this.chartEl, "--muted", "#9aa4b2");
    const gridStroke = cssVar(this.chartEl, "--border", "rgba(255,255,255,0.06)");
    const dateFmt = getDateFormat();
    const opts: Partial<uPlot.Options> = { padding: [8, hasTemp ? 56 : 16, 14, 0] };
    if (hasTemp) {
      series.push({ label: t("ui.forecast.seriesTemp"), stroke: muted, dash: [4, 3], scale: "temp" });
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
      cursorDateFormat: dateFmt,
      axisDateFormat: dateFmt,
      extraHooks: nowMarkerHooks(this.chartEl),
    });
    this.chartHasTemp = hasTemp;
  }

  render() {
    const f = this.forecast;
    const h = chartHeight();
    const hasData = f && f.solar.length > 0;
    const outlook = f?.cloudy_tomorrow
      ? t("ui.forecast.cloudyTomorrow")
      : f?.degraded
        ? t("ui.forecast.degraded")
        : t("ui.history.dash");
    const fresh = this.freshnessLabel();

    return html`
      <div class="card chart-card">
        <div class="head">
          <h3 style="margin:0">${t("ui.forecast.title")}</h3>
          <div class="head-actions">
            ${fresh ? html`<span class="updated">${t("ui.forecast.updatedAgo", { label: fresh })}</span>` : null}
            ${this.role === "admin"
              ? html`<button type="button" ?disabled=${this.refreshing} @click=${() => void this.refresh()}>&#8635; ${t("ui.forecast.refresh")}</button>`
              : null}
          </div>
        </div>
        <div class="metrics">
          <div class="metric-card">
            <div class="label">${t("ui.forecast.today")}</div>
            <div class="v">${f ? f.solar_today_kwh.toFixed(1) : "--"} kWh</div>
          </div>
          <div class="metric-card">
            <div class="label">${t("ui.forecast.tomorrow")}</div>
            <div class="v">${f ? f.solar_tomorrow_kwh.toFixed(1) : "--"} kWh</div>
          </div>
          <div class="metric-card">
            <div class="label">${t("ui.forecast.outlook")}</div>
            <div class="v">${outlook}</div>
          </div>
        </div>
        <div class="legend">
          <span class="swatch"><i style="background:var(--accent)"></i>${t("ui.forecast.solar")}</span>
          <span class="swatch"><i style="background:var(--accent-2)"></i>${t("ui.forecast.load")}</span>
          ${f && f.temperature && f.temperature.length > 0
            ? html`<span class="swatch"><i style="background:var(--muted)"></i>${t("ui.forecast.temp")}</span>`
            : null}
        </div>
        <div class="chart-panel">
          <div class="cursor-values"></div>
          <div class="chart-wrap" style="--chart-height:${h}px">
            <div class="chart-mount"></div>
          </div>
        </div>
        ${f?.degraded
          ? html`<div class="alert-strip">
              <span class="pill warn">${t("ui.forecast.degraded")}</span>
              <span>${(f.degraded_reasons ?? []).join("; ")}</span>
              ${this.role === "admin"
                ? html`<button type="button" @click=${this.openSettings}>${t("ui.forecast.configureForecast")} →</button>`
                : null}
            </div>`
          : null}
        ${!hasData
          ? html`<div class="empty-cta">
              <p class="label">${this.role === "viewer"
                ? t("ui.forecast.noForecastViewer")
                : t("ui.forecast.noForecastAdmin")}</p>
              ${this.role === "admin"
                ? html`<button type="button" class="primary" @click=${this.openSettings}>${t("ui.forecast.openSiteSettings")}</button>`
                : null}
            </div>`
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
