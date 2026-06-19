import { css } from "lit";
import uPlot from "uplot";

export interface SeriesDef {
  label: string;
  stroke: string;
  fill?: string;
  width?: number;
  dash?: number[];
  scale?: string;
}

export interface ChartHandle {
  get chart(): uPlot | null;
  destroy: () => void;
}

export type ChartOptions = Partial<uPlot.Options> & {
  showLegend?: boolean;
  cursorLegendEl?: HTMLElement | null;
};

export const CHART_HEIGHT_DESKTOP = 280;
export const CHART_HEIGHT_MOBILE = 240;
export const CHART_DEFAULT_PADDING: [number, number, number, number] = [8, 16, 14, 0];

const CHART_BREAKPOINT = "(max-width: 760px)";
const HEIGHT_INFLATION_GUARD_PX = 200;

/** Shared layout for forecast/history chart containers. */
export const chartContainerStyles = css`
  .chart-card {
    display: flex;
    flex-direction: column;
    min-height: min(50vh, 480px);
  }
  .chart-panel {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }
  .chart-wrap {
    flex: 1;
    width: 100%;
    min-height: var(--chart-height, 280px);
    position: relative;
    display: flex;
    flex-direction: column;
  }
  .chart-mount {
    flex: 1;
    min-height: 0;
    width: 100%;
    position: relative;
  }
  /* uPlot base layout (global uPlot.min.css does not pierce shadow DOM) */
  .chart-mount .uplot,
  .chart-mount .uplot *,
  .chart-mount .uplot *::before,
  .chart-mount .uplot *::after {
    box-sizing: border-box;
  }
  .chart-mount .uplot {
    position: relative;
    line-height: 1;
  }
  .chart-mount .u-wrap {
    position: relative;
    user-select: none;
  }
  .chart-mount .u-over,
  .chart-mount .u-under {
    position: absolute;
  }
  .chart-mount .u-under {
    overflow: hidden;
  }
  .chart-mount .uplot canvas {
    display: block;
    position: relative;
    width: 100%;
    height: 100%;
  }
  .chart-mount .u-axis {
    position: absolute;
  }
  .chart-mount .u-select {
    position: absolute;
    pointer-events: none;
  }
  .chart-mount .u-cursor-x,
  .chart-mount .u-cursor-y {
    position: absolute;
    left: 0;
    top: 0;
    pointer-events: none;
  }
`;

/** Responsive chart height used by forecast and history views (clamp 240px–360px, ~32vh). */
export function chartHeight(): number {
  if (typeof window === "undefined") return CHART_HEIGHT_DESKTOP;
  const vh = Math.round(window.innerHeight * 0.32);
  return Math.min(360, Math.max(240, vh));
}

/** Defer chart measurement until after layout (double rAF). */
export function scheduleChartRender(fn: () => void): void {
  requestAnimationFrame(() => requestAnimationFrame(fn));
}

function chartWrapEl(el: HTMLElement): HTMLElement | null {
  return el.classList.contains("chart-wrap")
    ? el
    : (el.closest(".chart-wrap") as HTMLElement | null);
}

function chartMountEl(el: HTMLElement): HTMLElement | null {
  return el.classList.contains("chart-mount")
    ? el
    : (el.closest(".chart-mount") as HTMLElement | null);
}

/** Parse --chart-height px value from a .chart-wrap element. */
export function parseChartHeightPx(wrap: HTMLElement): number | null {
  const cssH = getComputedStyle(wrap).getPropertyValue("--chart-height").trim();
  if (cssH.endsWith("px")) {
    const n = parseFloat(cssH);
    if (n > 0) return Math.round(n);
  }
  return null;
}

/** Measure container width; returns 0 when layout is not ready. */
export function measureChartWidth(el: HTMLElement): number {
  const wrap = chartWrapEl(el);
  if (wrap && wrap.clientWidth > 0) return wrap.clientWidth;
  if (el.clientWidth > 0) return el.clientWidth;
  const parent = el.parentElement;
  if (parent && parent.clientWidth > 0) return parent.clientWidth;
  return 0;
}

/**
 * Measure chart height from flex-assigned .chart-mount or --chart-height.
 * Never reads wrap.clientHeight (avoids uPlot inflation feedback loop).
 */
export function measureChartHeight(el: HTMLElement, minFallback?: number): number {
  const mount = chartMountEl(el);
  const wrap = chartWrapEl(el);
  const cssH = wrap ? parseChartHeightPx(wrap) : null;

  if (mount && mount.clientHeight > 0) {
    const h = mount.clientHeight;
    if (cssH != null && h > cssH + HEIGHT_INFLATION_GUARD_PX) return cssH;
    return h;
  }
  if (cssH != null) return cssH;
  return minFallback ?? chartHeight();
}

function observeTarget(el: HTMLElement): HTMLElement {
  return chartWrapEl(el) ?? el.parentElement ?? el;
}

/** Read a CSS custom property (theme token) resolved on `el`, with a fallback. */
export function cssVar(el: Element, name: string, fallback = ""): string {
  const v = getComputedStyle(el).getPropertyValue(name).trim();
  return v || fallback;
}

function formatCursorValue(val: number | null | undefined, label: string): string {
  if (val == null || Number.isNaN(val)) return "";
  const unit = label.includes("(%)") || label.includes("SOC") ? "%" : label.includes("°C") ? "°C" : " W";
  const rounded =
    unit === "°C" ? val.toFixed(1)
    : unit === "%" ? Math.round(val).toString()
    : Math.abs(val) >= 1000 ? `${(val / 1000).toFixed(2)}kW`
    : Math.round(val).toString();
  const short = label.replace(/\s*\([^)]*\)/, "").trim();
  return `${short} ${rounded}${unit === " W" ? "" : unit}`;
}

function cursorLegendHooks(el: HTMLElement | null | undefined): uPlot.Hooks.Arrays {
  if (!el) return {};
  return {
    setCursor: [
      (u: uPlot) => {
        const idx = u.cursor.idx;
        if (idx == null) {
          el.textContent = "";
          return;
        }
        const parts: string[] = [];
        for (let i = 1; i < u.series.length; i++) {
          const label = String(u.series[i]?.label ?? "");
          const v = u.data[i]?.[idx] as number | null | undefined;
          const part = formatCursorValue(v, label);
          if (part) parts.push(part);
        }
        el.textContent = parts.join(" · ");
      },
    ],
  };
}

// Create a uPlot time-series chart sized to its container. Axis/grid colors are
// pulled from the active theme tokens so the chart adapts to light/dark.
export function makeChart(
  el: HTMLElement,
  series: SeriesDef[],
  data: uPlot.AlignedData,
  opts: ChartOptions = {},
): ChartHandle {
  const axisStroke = cssVar(el, "--muted", "#9aa4b2");
  const gridStroke = cssVar(el, "--border", "rgba(255,255,255,0.06)");
  const axis = {
    stroke: axisStroke,
    grid: { stroke: gridStroke },
    ticks: { stroke: gridStroke },
  };
  const {
    showLegend = false,
    cursorLegendEl,
    series: optsSeries,
    axes: optsAxes,
    scales: optsScales,
    padding: optsPadding,
    legend: optsLegend,
    height: optsHeight,
    hooks: optsHooks,
    cursor: optsCursor,
    ...restOpts
  } = opts;
  const minHeightFallback = optsHeight ?? chartHeight();
  let currentHeight = minHeightFallback;
  const builtSeries =
    optsSeries ??
    [
      {},
      ...series.map((s) => ({
        label: s.label,
        stroke: s.stroke,
        fill: s.fill,
        width: s.width ?? 2,
        dash: s.dash,
        scale: s.scale,
      })),
    ];
  const cursorHooks = cursorLegendHooks(cursorLegendEl);

  let chart: uPlot | null = null;
  let lastObservedWidth = 0;
  const target = observeTarget(el);

  const syncSize = (remeasureHeight: boolean): void => {
    const width = measureChartWidth(el);
    if (width <= 0) return;
    if (remeasureHeight) {
      currentHeight = measureChartHeight(el, minHeightFallback);
    }
    if (!chart) {
      el.replaceChildren();
      const initialW = width;
      chart = new uPlot(buildOptions(width), data, el);
      requestAnimationFrame(() => {
        if (!chart) return;
        const w2 = measureChartWidth(el);
        const h2 = measureChartHeight(el, minHeightFallback);
        if (w2 > 0 && (w2 !== initialW || h2 !== currentHeight)) {
          currentHeight = h2;
          chart.setSize({ width: w2, height: currentHeight });
          lastObservedWidth = w2;
        }
      });
    } else {
      chart.setSize({ width, height: currentHeight });
    }
    lastObservedWidth = width;
  };

  const buildOptions = (width: number): uPlot.Options => ({
    ...restOpts,
    width,
    height: currentHeight,
    padding: optsPadding ?? CHART_DEFAULT_PADDING,
    legend: { show: showLegend, ...(optsLegend ?? {}) },
    cursor: {
      y: false,
      focus: { prox: 16 },
      ...(optsCursor ?? {}),
    },
    hooks: {
      ...(optsHooks ?? {}),
      setCursor: [...(optsHooks?.setCursor ?? []), ...(cursorHooks.setCursor ?? [])],
    },
    scales: optsScales ?? { x: { time: true } },
    axes: optsAxes ?? [axis, axis],
    series: builtSeries,
  });

  syncSize(true);

  const ro = new ResizeObserver(() => {
    const width = measureChartWidth(el);
    if (width <= 0) return;
    if (!chart) {
      syncSize(true);
      return;
    }
    const height = measureChartHeight(el, minHeightFallback);
    if (width !== lastObservedWidth || height !== currentHeight) {
      currentHeight = height;
      chart.setSize({ width, height: currentHeight });
      lastObservedWidth = width;
    }
  });
  ro.observe(target);

  const mql = window.matchMedia(CHART_BREAKPOINT);
  const onBreakpoint = () => syncSize(true);
  mql.addEventListener("change", onBreakpoint);

  return {
    get chart() {
      return chart;
    },
    destroy: () => {
      mql.removeEventListener("change", onBreakpoint);
      ro.disconnect();
      chart?.destroy();
      chart = null;
    },
  };
}
