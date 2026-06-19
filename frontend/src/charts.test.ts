import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

type ChartsModule = typeof import("./charts.js");

let charts: ChartsModule;

function mountChartDom(opts?: { wrapHeight?: string; mountHeight?: string }): {
  wrap: HTMLDivElement;
  mount: HTMLDivElement;
} {
  const wrap = document.createElement("div");
  wrap.className = "chart-wrap";
  wrap.style.setProperty("--chart-height", "300px");
  if (opts?.wrapHeight) wrap.style.height = opts.wrapHeight;

  const mount = document.createElement("div");
  mount.className = "chart-mount";
  if (opts?.mountHeight) mount.style.height = opts.mountHeight;

  wrap.appendChild(mount);
  document.body.appendChild(wrap);
  return { wrap, mount };
}

beforeAll(async () => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: false,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
  charts = await import("./charts.js");
});

describe("parseChartHeightPx", () => {
  it("parses --chart-height px values", () => {
    const { wrap } = mountChartDom();
    expect(charts.parseChartHeightPx(wrap)).toBe(300);
  });
});

describe("measureChartWidth", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("prefers .chart-wrap width over mount width", () => {
    const { wrap, mount } = mountChartDom();
    Object.defineProperty(wrap, "clientWidth", { configurable: true, value: 640 });
    Object.defineProperty(mount, "clientWidth", { configurable: true, value: 100 });
    expect(charts.measureChartWidth(mount)).toBe(640);
  });
});

describe("measureChartHeight", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("returns --chart-height when mount has no layout height", () => {
    const { mount } = mountChartDom();
    expect(charts.measureChartHeight(mount)).toBe(300);
  });

  it("uses mount clientHeight when flex-assigned", () => {
    const { mount } = mountChartDom({ mountHeight: "320px" });
    Object.defineProperty(mount, "clientHeight", { configurable: true, value: 320 });
    expect(charts.measureChartHeight(mount)).toBe(320);
  });

  it("does not grow when wrap clientHeight is artificially inflated", () => {
    const { mount, wrap } = mountChartDom({ wrapHeight: "600px" });
    Object.defineProperty(wrap, "clientHeight", { configurable: true, value: 600 });
    expect(charts.measureChartHeight(mount)).toBe(300);
  });

  it("caps mount height when it exceeds css var by inflation guard", () => {
    const { mount } = mountChartDom({ mountHeight: "520px" });
    Object.defineProperty(mount, "clientHeight", { configurable: true, value: 520 });
    expect(charts.measureChartHeight(mount)).toBe(300);
  });
});
