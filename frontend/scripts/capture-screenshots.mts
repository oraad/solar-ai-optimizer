/**
 * Capture dashboard screenshots for docs/frontend-manual.md.
 *
 * Prerequisite: demo stack running with seeded data.
 *
 * Local (after one-time `npm ci` + `npx playwright install chromium`):
 *   npm run docs:screenshots
 *
 * Docker (Playwright image + cached node_modules; from repo root or frontend):
 *   docker compose --profile docs run --rm docs-screenshots
 *   npm run docs:screenshots:docker
 *
 * First Docker use or after package-lock.json changes:
 *   docker compose --profile docs run --rm docs-screenshots npm ci
 */
import { mkdirSync } from "node:fs";

import { chromium, type Page } from "playwright";

import {
  app,
  assertDemoPreflight,
  BASE_URL,
  clickMainTab,
  clickSettingsNav,
  createScreenshotContext,
  initDashboard,
  MOBILE_VIEWPORT,
  OUT_DIR,
  selectSettingsCategory,
  shotApp,
  shotFull,
  shotLayout,
  shotLocator,
  VIEWER_HEADERS,
  waitForHistoryDecisionsReady,
  waitForOverviewReady,
  waitForSettingsReady,
} from "./screenshot-utils.mjs";

async function captureAdmin(page: Page): Promise<void> {
  await initDashboard(page);

  await clickMainTab(page, "Overview");
  await shotLayout(page, OUT_DIR, "overview.png");

  await clickMainTab(page, "Forecast");
  await shotLayout(page, OUT_DIR, "forecast.png");

  await clickMainTab(page, "History");
  await shotLayout(page, OUT_DIR, "history-chart.png");
  await app(page)
    .locator("solar-history-view .tabs button")
    .filter({ hasText: "Decisions" })
    .click();
  await waitForHistoryDecisionsReady(page);
  await shotLayout(page, OUT_DIR, "history-decisions.png");

  await clickMainTab(page, "Assistant");
  await shotLayout(page, OUT_DIR, "assistant.png");

  await clickMainTab(page, "Load shedding");
  await shotLayout(page, OUT_DIR, "load-shedding.png");
  const tierCard = app(page).locator("solar-load-shedding-panel .tier-card").first();
  await tierCard.locator(".tier-head").click();
  await tierCard.locator(".tier-body").waitFor({ state: "visible", timeout: 30_000 });
  await shotLocator(tierCard, OUT_DIR, "settings-load-shedding.png");

  await clickMainTab(page, "Settings");
  await clickSettingsNav(page, "Engine");
  await waitForSettingsReady(page);
  await shotFull(page, OUT_DIR, "settings.png");

  await clickMainTab(page, "Overview");
  await waitForOverviewReady(page);
  await shotLocator(app(page).locator("solar-overrides-panel").first(), OUT_DIR, "overrides.png");
}

async function captureViewer(page: Page): Promise<void> {
  await initDashboard(page);
  await app(page).locator(".pill.warn").filter({ hasText: "VIEWER" }).waitFor({ state: "visible", timeout: 30_000 });
  await clickMainTab(page, "Overview");
  await shotLayout(page, OUT_DIR, "viewer-overview.png");
}

async function captureMobile(page: Page): Promise<void> {
  await initDashboard(page);

  await clickMainTab(page, "Overview");
  await shotApp(page, OUT_DIR, "mobile-overview.png");

  await clickMainTab(page, "History");
  await shotLayout(page, OUT_DIR, "mobile-history-chart.png");
  await app(page)
    .locator("solar-history-view .tabs button")
    .filter({ hasText: "Decisions" })
    .click();
  await waitForHistoryDecisionsReady(page);
  await shotLayout(page, OUT_DIR, "mobile-history-decisions.png");

  await clickMainTab(page, "Shedding");
  await shotApp(page, OUT_DIR, "mobile-load-shedding.png");

  await clickMainTab(page, "Settings");
  await selectSettingsCategory(page, "Engine");
  await waitForSettingsReady(page);
  await shotApp(page, OUT_DIR, "mobile-settings.png");
}

async function main(): Promise<void> {
  mkdirSync(OUT_DIR, { recursive: true });
  await assertDemoPreflight(BASE_URL);

  const browser = await chromium.launch();

  const adminContext = await createScreenshotContext(browser, {
    viewport: { width: 1280, height: 900 },
  });
  const adminPage = await adminContext.newPage();

  const viewerContext = await createScreenshotContext(browser, {
    viewport: { width: 1280, height: 900 },
    extraHTTPHeaders: VIEWER_HEADERS,
  });
  const viewerPage = await viewerContext.newPage();

  const mobileContext = await createScreenshotContext(browser, {
    viewport: MOBILE_VIEWPORT,
    isMobile: true,
    hasTouch: true,
  });
  const mobilePage = await mobileContext.newPage();

  try {
    await captureAdmin(adminPage);
    await captureViewer(viewerPage);
    await captureMobile(mobilePage);
  } finally {
    await adminContext.close();
    await viewerContext.close();
    await mobileContext.close();
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
