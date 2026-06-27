/**
 * Verify forecast/history chart layout: no overflow, axes visible, canvas aligned, card fill.
 *
 * Prerequisite: solar app running (docker compose up -d solar).
 *
 * Local: npm run test:charts-visual
 * Docker: npm run test:charts-visual:docker
 *         (or docker compose --profile docs run --rm docs-screenshots npm run test:charts-visual)
 */
import { mkdirSync } from "node:fs";
import path from "node:path";

import { chromium, type Locator, type Page } from "playwright";

import {
  app,
  assertDemoPreflight,
  BASE_URL,
  clickMainTab,
  createScreenshotContext,
  initDashboard,
  OUT_DIR,
  waitForChart,
} from "./screenshot-utils.mjs";

const TOLERANCE_PX = 2;

type Rect = { top: number; left: number; bottom: number; right: number; width: number; height: number };

type LayoutProbe = {
  ok: boolean;
  errors: string[];
  rects: Record<string, Rect>;
};

async function probeChartLayout(host: Locator): Promise<LayoutProbe> {
  return host.evaluate((el) => {
    const root = (el as HTMLElement).shadowRoot;
    const errors: string[] = [];
    const rects: Record<string, { top: number; left: number; bottom: number; right: number; width: number; height: number }> = {};
    const tol = 2;

    const card = root?.querySelector(".card");
    const wrap = root?.querySelector(".chart-wrap");
    const mount = root?.querySelector(".chart-mount");
    const uplot = wrap?.querySelector(".uplot");
    const under = wrap?.querySelector(".u-under");

    if (!card) errors.push("card missing");
    if (!wrap) errors.push("wrap missing");
    if (!mount) errors.push("mount missing");

    const cardR = card?.getBoundingClientRect();
    const wrapR = wrap?.getBoundingClientRect();
    const mountR = mount?.getBoundingClientRect();
    const uplotR = uplot?.getBoundingClientRect();
    const underR = under?.getBoundingClientRect();

    if (cardR) {
      rects.card = { top: cardR.top, left: cardR.left, bottom: cardR.bottom, right: cardR.right, width: cardR.width, height: cardR.height };
    }
    if (wrapR) {
      rects.wrap = { top: wrapR.top, left: wrapR.left, bottom: wrapR.bottom, right: wrapR.right, width: wrapR.width, height: wrapR.height };
    }
    if (mountR) {
      rects.mount = { top: mountR.top, left: mountR.left, bottom: mountR.bottom, right: mountR.right, width: mountR.width, height: mountR.height };
    }
    if (uplotR) {
      rects.uplot = { top: uplotR.top, left: uplotR.left, bottom: uplotR.bottom, right: uplotR.right, width: uplotR.width, height: uplotR.height };
    }
    if (underR) {
      rects.under = { top: underR.top, left: underR.left, bottom: underR.bottom, right: underR.right, width: underR.width, height: underR.height };
    }

    if (!wrapR || !cardR) {
      return { ok: false, errors, rects };
    }

    if (wrap && wrap.scrollHeight > wrap.clientHeight + 1) {
      errors.push(
        "scroll overflow: scrollHeight=" + wrap.scrollHeight + " clientHeight=" + wrap.clientHeight,
      );
    }

    const axes = wrap ? [...wrap.querySelectorAll(".u-axis")] : [];
    for (let i = 0; i < axes.length; i++) {
      const ar = axes[i].getBoundingClientRect();
      rects["axis" + i] = {
        top: ar.top,
        left: ar.left,
        bottom: ar.bottom,
        right: ar.right,
        width: ar.width,
        height: ar.height,
      };
      if (ar.bottom > wrapR.bottom + tol) {
        errors.push("axis" + i + " bottom spill: " + ar.bottom.toFixed(1) + " > wrap " + wrapR.bottom.toFixed(1));
      }
      if (ar.top < wrapR.top - tol) {
        errors.push("axis" + i + " top spill: " + ar.top.toFixed(1) + " < wrap " + wrapR.top.toFixed(1));
      }
    }

    if (uplotR) {
      if (uplotR.bottom > wrapR.bottom + tol) {
        errors.push("uplot bottom spill: " + uplotR.bottom.toFixed(1) + " > wrap " + wrapR.bottom.toFixed(1));
      }
      if (uplotR.top < wrapR.top - tol) {
        errors.push("uplot top spill: " + uplotR.top.toFixed(1) + " < wrap " + wrapR.top.toFixed(1));
      }
    }

    if (underR) {
      if (underR.top < wrapR.top - tol) {
        errors.push("canvas too high: under.top=" + underR.top.toFixed(1) + " wrap.top=" + wrapR.top.toFixed(1));
      }
      if (underR.top > wrapR.top + 80 + tol) {
        errors.push("canvas shifted down: under.top=" + underR.top.toFixed(1) + " wrap.top=" + wrapR.top.toFixed(1));
      }
      if (underR.bottom > wrapR.bottom - 14 + tol) {
        errors.push("canvas bottom too low: under.bottom=" + underR.bottom.toFixed(1) + " wrap.bottom=" + wrapR.bottom.toFixed(1));
      }
    }

    const header = root?.querySelector(".head");
    const headerBottom = header?.getBoundingClientRect().bottom ?? cardR.top;
    const cardBodyHeight = cardR.bottom - headerBottom;
    if (cardBodyHeight > 0 && wrapR.height / cardBodyHeight < 0.35) {
      errors.push(
        "chart fill low: wrap.height=" + wrapR.height.toFixed(0) + " / cardBody=" + cardBodyHeight.toFixed(0) + " = " + (wrapR.height / cardBodyHeight).toFixed(2),
      );
    }

    if (mountR && mountR.height < 100) {
      errors.push("mount too short: " + mountR.height.toFixed(0) + "px");
    }

    return { ok: errors.length === 0, errors, rects };
  });
}

function reportProbe(label: string, probe: LayoutProbe): void {
  if (probe.ok) {
    console.log(`OK ${label}: layout probes passed`);
    return;
  }
  console.error(`${label} layout errors:`);
  for (const e of probe.errors) console.error(`  - ${e}`);
  console.error("Rects:", JSON.stringify(probe.rects, null, 2));
  throw new Error(`${label}: ${probe.errors.join("; ")}`);
}

async function verifyChartInComponent(
  page: Page,
  componentSelector: string,
  wrapShot: string,
  cardShot: string,
  label: string,
): Promise<void> {
  await waitForChart(page, componentSelector);
  const host = app(page).locator(componentSelector);
  const wrap = host.locator(".chart-wrap").first();

  const probe = await probeChartLayout(host);
  reportProbe(label, probe);

  await wrap.screenshot({ path: path.join(OUT_DIR, wrapShot), animations: "disabled" });
  console.log(`wrote ${path.join(OUT_DIR, wrapShot)}`);

  await host.locator(".card").first().screenshot({
    path: path.join(OUT_DIR, cardShot),
    animations: "disabled",
  });
  console.log(`wrote ${path.join(OUT_DIR, cardShot)}`);
}

async function main(): Promise<void> {
  mkdirSync(OUT_DIR, { recursive: true });
  await assertDemoPreflight(BASE_URL);

  const browser = await chromium.launch();
  const context = await createScreenshotContext(browser, {
    viewport: { width: 1280, height: 900 },
  });
  const page = await context.newPage();

  try {
    await initDashboard(page);

    await clickMainTab(page, "Forecast");
    await verifyChartInComponent(
      page,
      "solar-forecast-chart",
      "chart-verify-forecast.png",
      "chart-verify-forecast-card.png",
      "Forecast",
    );

    await clickMainTab(page, "History");
    await verifyChartInComponent(
      page,
      "solar-history-view",
      "chart-verify-history.png",
      "chart-verify-history-card.png",
      "History",
    );
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
