import { afterEach, describe, expect, it } from "vitest";

import {
  formatChartAxisLabels,
  formatChartCursor,
  formatDateTime,
  getDateFormat,
  getDisplayTimezone,
  setDateFormat,
  setSiteTimezone,
  type DateDisplayFormat,
} from "./date-format.js";

const SAMPLE_ISO = "2026-06-24T15:30:00Z";
const SAMPLE_UNIX = Math.floor(new Date(SAMPLE_ISO).getTime() / 1000);

function localUnix(y: number, m: number, d: number, h: number, min = 0): number {
  return Math.floor(new Date(y, m, d, h, min).getTime() / 1000);
}

describe("formatDateTime", () => {
  afterEach(() => {
    localStorage.removeItem("solar-date-format");
  });

  it("formats ddmmyy with zero-padded day/month and 2-digit year", () => {
    expect(formatDateTime(SAMPLE_ISO, "ddmmyy")).toBe("24/06/26 15:30");
  });

  it("formats iso as YYYY-MM-DD HH:mm", () => {
    expect(formatDateTime(SAMPLE_ISO, "iso")).toBe("2026-06-24 15:30");
  });

  it("formats locale with Intl when locale mode is selected", () => {
    const out = formatDateTime(SAMPLE_ISO, "locale");
    expect(out.length).toBeGreaterThan(0);
    expect(out).toMatch(/2026|24|06|15|30/);
  });
});

describe("formatChartAxisLabels", () => {
  it("shows date only on first tick", () => {
    const labels = formatChartAxisLabels([SAMPLE_UNIX, SAMPLE_UNIX + 3600], "iso");
    expect(labels[0]).toBe("2026-06-24");
    expect(labels[1]).toMatch(/^\d{2}:\d{2}$/);
  });

  it("shows date on day boundary and hours elsewhere", () => {
    const day1 = localUnix(2026, 5, 24, 8);
    const day1Later = localUnix(2026, 5, 24, 14);
    const day2 = localUnix(2026, 5, 25, 8);
    const labels = formatChartAxisLabels([day1, day1Later, day2], "iso");
    expect(labels[0]).toBe("2026-06-24");
    expect(labels[1]).toBe("14:00");
    expect(labels[2]).toBe("2026-06-25");
  });

  it("uses ddmmyy date style when requested", () => {
    const labels = formatChartAxisLabels([SAMPLE_UNIX], "ddmmyy");
    expect(labels[0]).toBe("24/06/26");
  });
});

describe("formatChartCursor", () => {
  it("always includes time", () => {
    expect(formatChartCursor(SAMPLE_UNIX, "iso")).toBe("2026-06-24 15:30");
  });
});

describe("site timezone", () => {
  afterEach(() => {
    setSiteTimezone(null, null);
  });

  it("uses explicit site timezone for iso formatting", () => {
    setSiteTimezone("Africa/Johannesburg", null);
    expect(getDisplayTimezone()).toBe("Africa/Johannesburg");
    expect(formatDateTime(SAMPLE_ISO, "iso")).toBe("2026-06-24 17:30");
  });

  it("uses resolved timezone when config is auto", () => {
    setSiteTimezone("auto", "Africa/Johannesburg");
    expect(getDisplayTimezone()).toBe("Africa/Johannesburg");
    expect(formatDateTime(SAMPLE_ISO, "ddmmyy")).toBe("24/06/26 17:30");
  });

  it("falls back to browser local when auto is unresolved", () => {
    setSiteTimezone("auto", null);
    expect(getDisplayTimezone()).toBeUndefined();
  });

  it("dispatches solar-site-timezone-change when effective timezone changes", () => {
    let fired = false;
    window.addEventListener("solar-site-timezone-change", () => {
      fired = true;
    });
    setSiteTimezone("Europe/Berlin", null);
    expect(fired).toBe(true);
  });
});

describe("getDateFormat / setDateFormat", () => {
  afterEach(() => {
    localStorage.removeItem("solar-date-format");
  });

  it("defaults to locale", () => {
    expect(getDateFormat()).toBe("locale");
  });

  it("persists preference in localStorage", () => {
    setDateFormat("iso");
    expect(getDateFormat()).toBe("iso");
    expect(localStorage.getItem("solar-date-format")).toBe("iso");
  });

  it("dispatches solar-date-format-change", () => {
    let fired = false;
    window.addEventListener("solar-date-format-change", () => {
      fired = true;
    });
    setDateFormat("ddmmyy" as DateDisplayFormat);
    expect(fired).toBe(true);
  });
});
