import { afterEach, describe, expect, it } from "vitest";

import {
  formatChartAxis,
  formatChartCursor,
  formatDateTime,
  getDateFormat,
  setDateFormat,
  type DateDisplayFormat,
} from "./date-format.js";

const SAMPLE_ISO = "2026-06-24T15:30:00Z";
const SAMPLE_UNIX = Math.floor(new Date(SAMPLE_ISO).getTime() / 1000);

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

describe("formatChartAxis", () => {
  it("shows date only when span exceeds one day", () => {
    expect(formatChartAxis(SAMPLE_UNIX, "ddmmyy", 86400 * 2)).toBe("24/06/26");
    expect(formatChartAxis(SAMPLE_UNIX, "iso", 86400 * 2)).toBe("2026-06-24");
  });

  it("includes time when span is one day or less", () => {
    expect(formatChartAxis(SAMPLE_UNIX, "ddmmyy", 3600)).toBe("24/06/26 15:30");
    expect(formatChartAxis(SAMPLE_UNIX, "iso", 3600)).toBe("2026-06-24 15:30");
  });
});

describe("formatChartCursor", () => {
  it("always includes time", () => {
    expect(formatChartCursor(SAMPLE_UNIX, "iso")).toBe("2026-06-24 15:30");
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
