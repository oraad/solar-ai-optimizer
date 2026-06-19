/**
 * Capture dashboard screenshots for docs/frontend-manual.md.
 *
 * Prerequisite: demo stack running with seeded data.
 * Usage: npm run docs:screenshots
 */
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium, type Page } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.resolve(__dirname, "../../docs/images/frontend");
const BASE_URL = process.env.SCREENSHOT_BASE_URL ?? "http://localhost:8000";

const VIEWER_HEADERS = {
  "X-Remote-User-Id": "viewer-demo",
  "X-Remote-User-Name": "viewer",
  "X-Remote-User-Display-Name": "Demo Viewer",
};

function app(page: Page) {
  return page.locator("solar-app");
}

async function waitForDashboard(page: Page): Promise<void> {
  await page.goto(BASE_URL, { waitUntil: "domcontentloaded", timeout: 60_000 });
  await page.evaluate(() => {
    localStorage.setItem("solar-theme", "dark");
    document.documentElement.setAttribute("data-theme", "dark");
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await app(page).getByRole("tablist").waitFor({ timeout: 60_000 });
  await page.waitForTimeout(1500);
}

async function clickMainTab(page: Page, label: string): Promise<void> {
  await app(page).getByRole("tab", { name: label }).click();
  await page.waitForTimeout(900);
}

async function shot(page: Page, name: string): Promise<void> {
  const file = path.join(OUT_DIR, name);
  await app(page).locator(".layout").first().screenshot({ path: file });
  console.log(`wrote ${file}`);
}

async function shotFull(page: Page, name: string): Promise<void> {
  const file = path.join(OUT_DIR, name);
  await page.screenshot({ path: file, fullPage: true });
  console.log(`wrote ${file}`);
}

async function expandDetails(page: Page, summaryText: string): Promise<void> {
  const summary = app(page).locator("solar-settings-panel details summary").filter({
    hasText: summaryText,
  }).first();
  const details = summary.locator("xpath=ancestor::details[1]");
  const open = await details.evaluate((el) => (el as HTMLDetailsElement).open);
  if (!open) {
    await summary.click();
    await page.waitForTimeout(300);
  }
}

async function captureAdmin(page: Page): Promise<void> {
  await waitForDashboard(page);

  await clickMainTab(page, "Overview");
  await shot(page, "overview.png");

  await clickMainTab(page, "Forecast");
  await shot(page, "forecast.png");

  await clickMainTab(page, "History");
  await shot(page, "history-chart.png");
  await app(page)
    .locator("solar-history-view .tabs button")
    .filter({ hasText: "Decisions" })
    .click();
  await page.waitForTimeout(500);
  await shot(page, "history-decisions.png");

  await clickMainTab(page, "Assistant");
  await shot(page, "assistant.png");

  await clickMainTab(page, "Settings");
  await expandDetails(page, "Home Assistant");
  await expandDetails(page, "Load shedding");
  await expandDetails(page, "Inverter entity map");
  await shotFull(page, "settings.png");
  const tierBlock = app(page)
    .locator("solar-settings-panel details")
    .filter({ hasText: "Load-shedding tiers" })
    .first();
  await tierBlock.screenshot({ path: path.join(OUT_DIR, "settings-load-shedding.png") });
  console.log(`wrote ${path.join(OUT_DIR, "settings-load-shedding.png")}`);

  await clickMainTab(page, "Overview");
  await app(page)
    .locator("solar-overrides-panel")
    .first()
    .screenshot({ path: path.join(OUT_DIR, "overrides.png") });
  console.log(`wrote ${path.join(OUT_DIR, "overrides.png")}`);
}

async function captureViewer(page: Page): Promise<void> {
  await waitForDashboard(page);
  await clickMainTab(page, "Overview");
  await shot(page, "viewer-overview.png");
}

async function main(): Promise<void> {
  mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch();

  const adminContext = await browser.newContext({
    locale: "en-US",
    timezoneId: "UTC",
    viewport: { width: 1280, height: 900 },
  });
  const adminPage = await adminContext.newPage();

  const viewerContext = await browser.newContext({
    locale: "en-US",
    timezoneId: "UTC",
    viewport: { width: 1280, height: 900 },
    extraHTTPHeaders: VIEWER_HEADERS,
  });
  const viewerPage = await viewerContext.newPage();

  try {
    await captureAdmin(adminPage);
    await captureViewer(viewerPage);
  } finally {
    await adminContext.close();
    await viewerContext.close();
    await browser.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
