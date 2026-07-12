/**
 * Shared Playwright helpers for docs screenshots and chart visual checks.
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

import type { Browser, BrowserContextOptions, Locator, Page } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const OUT_DIR = path.resolve(__dirname, "../../docs/images/frontend");
export const BASE_URL = process.env.SCREENSHOT_BASE_URL ?? "http://localhost:8000";
export const MOBILE_VIEWPORT = { width: 390, height: 844 };

export const VIEWER_HEADERS = {
  "X-Remote-User-Id": "viewer-demo",
  "X-Remote-User-Name": "viewer",
  "X-Remote-User-Display-Name": "Demo Viewer",
};

const SCREENSHOT_OPTS = { animations: "disabled" as const };

export function app(page: Page) {
  return page.locator("solar-app");
}

export async function assertDemoPreflight(baseUrl: string = BASE_URL): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${baseUrl}/api/status`, { signal: AbortSignal.timeout(15_000) });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    throw new Error(
      `Demo preflight failed: cannot reach ${baseUrl}/api/status (${msg}). ` +
        "Start the demo stack and seed data first.",
    );
  }
  if (!res.ok) {
    throw new Error(`Demo preflight failed: GET /api/status returned ${res.status}`);
  }
  const data = (await res.json()) as { telemetry?: unknown; decision?: unknown };
  if (!data.telemetry) {
    throw new Error("Demo preflight failed: /api/status has no telemetry (is DEMO_MODE enabled and seeded?)");
  }
}

export async function createScreenshotContext(
  browser: Browser,
  opts: Pick<BrowserContextOptions, "viewport" | "extraHTTPHeaders" | "isMobile" | "hasTouch">,
) {
  return browser.newContext({
    locale: "en-US",
    timezoneId: "UTC",
    reducedMotion: "reduce",
    ...opts,
  });
}

export async function preparePage(page: Page, baseUrl: string = BASE_URL): Promise<void> {
  await page.goto(baseUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
  await page.evaluate(() => {
    localStorage.setItem("solar-theme", "dark");
    localStorage.setItem("solar-tab", "overview");
    document.documentElement.setAttribute("data-theme", "dark");
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(
    () => {
      const splash = document.getElementById("boot-splash");
      return !splash || splash.classList.contains("boot-splash-out");
    },
    { timeout: 60_000 },
  );
  await app(page).getByRole("tablist").waitFor({ timeout: 60_000 });
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
}

export async function waitForDashboardReady(page: Page): Promise<void> {
  await page.locator('solar-app[data-dashboard-ready="true"]').waitFor({ timeout: 60_000 });
  await app(page).locator("solar-status-cards .skeleton-tile").waitFor({ state: "hidden", timeout: 60_000 });
}

export async function waitForOverviewReady(page: Page): Promise<void> {
  await app(page)
    .locator("solar-decision-panel")
    .getByText("Waiting for first decision...")
    .waitFor({ state: "hidden", timeout: 60_000 });
  await app(page).locator("solar-overrides-panel").waitFor({ state: "visible", timeout: 30_000 });
}

export async function waitForChart(page: Page, hostSelector: string): Promise<void> {
  const host = app(page).locator(hostSelector);
  const wrap = host.locator(".chart-wrap").first();
  const uplot = wrap.locator(".uplot").first();
  await wrap.waitFor({ state: "visible", timeout: 30_000 });
  await uplot.waitFor({ state: "visible", timeout: 30_000 });
}

export async function waitForSettingsReady(page: Page): Promise<void> {
  await app(page)
    .locator("solar-settings-panel")
    .getByText("Loading config...")
    .waitFor({ state: "hidden", timeout: 60_000 });
}

export async function waitForHistoryDecisionsReady(page: Page): Promise<void> {
  const panel = app(page).locator("solar-history-view");
  await panel.getByText("No decisions recorded yet.").waitFor({ state: "hidden", timeout: 60_000 });
  await panel.locator("table tbody tr").first().waitFor({ state: "visible", timeout: 30_000 });
}

async function waitForLoadSheddingReady(page: Page): Promise<void> {
  await waitForSettingsReady(page);
  await app(page).locator("solar-load-shedding-panel .tier-card").first().waitFor({ state: "visible", timeout: 30_000 });
}

async function waitForTabReady(page: Page, label: string): Promise<void> {
  switch (label) {
    case "Overview":
      await waitForOverviewReady(page);
      break;
    case "Forecast":
      await waitForChart(page, "solar-forecast-chart");
      break;
    case "History":
      await waitForChart(page, "solar-history-view");
      break;
    case "Load shedding":
    case "Shedding":
      await waitForLoadSheddingReady(page);
      break;
    case "Settings":
      await waitForSettingsReady(page);
      break;
    default:
      break;
  }
}

export async function clickMainTab(page: Page, label: string): Promise<void> {
  await app(page).getByRole("tab", { name: label }).click();
  await waitForTabReady(page, label);
}

export async function clickSettingsNav(page: Page, label: string): Promise<void> {
  await app(page)
    .locator("solar-settings-panel .settings-nav-desktop .nav-item")
    .filter({ hasText: label })
    .first()
    .click();
  await page.waitForTimeout(200);
}

export async function selectSettingsCategory(page: Page, category: string): Promise<void> {
  await app(page)
    .locator("solar-settings-panel .category-pills button")
    .filter({ hasText: category })
    .first()
    .click();
  await page.waitForTimeout(200);
}

export async function initDashboard(page: Page, baseUrl: string = BASE_URL): Promise<void> {
  await preparePage(page, baseUrl);
  await waitForDashboardReady(page);
}

export async function shotLayout(page: Page, outDir: string, name: string): Promise<void> {
  const file = path.join(outDir, name);
  await app(page).locator(".layout").first().screenshot({ path: file, ...SCREENSHOT_OPTS });
  console.log(`wrote ${file}`);
}

/** Clip to topbar + main `.layout` (avoids phantom page scroll below content). */
async function appContentClip(page: Page): Promise<{ x: number; y: number; width: number; height: number } | null> {
  return page.evaluate(() => {
    const app = document.querySelector("solar-app");
    if (!app) return null;
    const root = app.shadowRoot;
    if (!root) return null;

    const topbar = root.querySelector(".topbar");
    const layout = root.querySelector(".layout");
    if (!topbar || !layout) return null;

    const topRect = topbar.getBoundingClientRect();
    const layoutRect = layout.getBoundingClientRect();
    const top = topRect.top + window.scrollY;
    const bottom = layoutRect.bottom + window.scrollY;
    const height = Math.ceil(bottom - topRect.top);
    if (height <= 0 || topRect.width <= 0) return null;

    return { x: topRect.left + window.scrollX, y: top, width: topRect.width, height };
  });
}

export async function shotApp(page: Page, outDir: string, name: string): Promise<void> {
  const file = path.join(outDir, name);
  await page.evaluate(() => window.scrollTo(0, 0));

  let clip = await appContentClip(page);
  if (!clip) {
    await app(page).screenshot({ path: file, ...SCREENSHOT_OPTS });
    console.log(`wrote ${file}`);
    return;
  }

  const originalViewport = page.viewportSize() ?? MOBILE_VIEWPORT;
  await page.setViewportSize({
    width: Math.ceil(clip.width),
    height: Math.ceil(clip.height),
  });
  await page.waitForTimeout(100);
  await page.evaluate(() => window.scrollTo(0, 0));

  clip = await appContentClip(page);
  if (clip) {
    await page.screenshot({
      path: file,
      clip: { x: clip.x, y: clip.y, width: clip.width, height: clip.height },
      ...SCREENSHOT_OPTS,
    });
  } else {
    await page.screenshot({ path: file, ...SCREENSHOT_OPTS });
  }

  await page.setViewportSize(originalViewport);
  console.log(`wrote ${file}`);
}

export async function shotFull(page: Page, outDir: string, name: string): Promise<void> {
  const file = path.join(outDir, name);
  await page.screenshot({ path: file, fullPage: true, ...SCREENSHOT_OPTS });
  console.log(`wrote ${file}`);
}

export async function shotLocator(locator: Locator, outDir: string, name: string): Promise<void> {
  const file = path.join(outDir, name);
  await locator.screenshot({ path: file, ...SCREENSHOT_OPTS });
  console.log(`wrote ${file}`);
}
