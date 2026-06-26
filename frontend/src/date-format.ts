import { getLocale } from "./i18n.js";

export type DateDisplayFormat = "locale" | "ddmmyy" | "iso";

const STORAGE_KEY = "solar-date-format";
const VALID: DateDisplayFormat[] = ["locale", "ddmmyy", "iso"];

let siteTimezoneConfig: string | null = null;
let siteTimezoneResolved: string | null = null;

export function setSiteTimezone(config: string | null, resolved: string | null): void {
  const prev = getDisplayTimezone();
  siteTimezoneConfig = config;
  siteTimezoneResolved = resolved;
  const next = getDisplayTimezone();
  if (prev !== next && typeof window !== "undefined") {
    window.dispatchEvent(new Event("solar-site-timezone-change"));
  }
}

/** Effective IANA timezone for display, or undefined for browser local. */
export function getDisplayTimezone(): string | undefined {
  const cfg = (siteTimezoneConfig ?? "auto").trim();
  if (cfg && cfg.toLowerCase() !== "auto") return cfg;
  return siteTimezoneResolved ?? undefined;
}

export function getDateFormat(): DateDisplayFormat {
  if (typeof localStorage === "undefined") return "locale";
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v && VALID.includes(v as DateDisplayFormat)) return v as DateDisplayFormat;
  } catch {
    /* ignore */
  }
  return "locale";
}

export function setDateFormat(fmt: DateDisplayFormat): void {
  try {
    localStorage.setItem(STORAGE_KEY, fmt);
  } catch {
    /* ignore */
  }
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("solar-date-format-change"));
  }
}

function toDate(input: Date | string | number): Date | null {
  if (input instanceof Date) {
    return Number.isNaN(input.getTime()) ? null : input;
  }
  const d =
    typeof input === "number"
      ? new Date(input < 1e12 ? input * 1000 : input)
      : new Date(input);
  return Number.isNaN(d.getTime()) ? null : d;
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

type DateParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
};

function partsInTimezone(date: Date, timeZone?: string): DateParts {
  if (!timeZone) {
    return {
      year: date.getFullYear(),
      month: date.getMonth() + 1,
      day: date.getDate(),
      hour: date.getHours(),
      minute: date.getMinutes(),
    };
  }
  const fmt = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const mapped = Object.fromEntries(
    fmt.formatToParts(date).map((p) => [p.type, p.value]),
  );
  return {
    year: Number(mapped.year),
    month: Number(mapped.month),
    day: Number(mapped.day),
    hour: Number(mapped.hour),
    minute: Number(mapped.minute),
  };
}

function formatDdmmyy(date: Date, includeTime: boolean, timeZone?: string): string {
  const p = partsInTimezone(date, timeZone);
  const dd = pad2(p.day);
  const mm = pad2(p.month);
  const yy = pad2(p.year % 100);
  if (!includeTime) return `${dd}/${mm}/${yy}`;
  return `${dd}/${mm}/${yy} ${pad2(p.hour)}:${pad2(p.minute)}`;
}

function formatIso(date: Date, includeTime: boolean, timeZone?: string): string {
  const p = partsInTimezone(date, timeZone);
  const y = String(p.year);
  const m = pad2(p.month);
  const d = pad2(p.day);
  if (!includeTime) return `${y}-${m}-${d}`;
  return `${y}-${m}-${d} ${pad2(p.hour)}:${pad2(p.minute)}`;
}

function formatLocale(date: Date, includeTime: boolean, timeZone?: string): string {
  const locale = getLocale();
  const opts: Intl.DateTimeFormatOptions = timeZone ? { timeZone } : {};
  if (includeTime) {
    return new Intl.DateTimeFormat(locale, {
      ...opts,
      dateStyle: "short",
      timeStyle: "short",
    }).format(date);
  }
  return new Intl.DateTimeFormat(locale, {
    ...opts,
    dateStyle: "short",
  }).format(date);
}

function formatWithMode(
  date: Date,
  fmt: DateDisplayFormat,
  includeTime: boolean,
  timeZone?: string,
): string {
  switch (fmt) {
    case "ddmmyy":
      return formatDdmmyy(date, includeTime, timeZone);
    case "iso":
      return formatIso(date, includeTime, timeZone);
    default:
      return formatLocale(date, includeTime, timeZone);
  }
}

export function formatDateTime(
  input: Date | string | number,
  fmt?: DateDisplayFormat,
): string {
  const d = toDate(input);
  if (!d) return String(input);
  return formatWithMode(d, fmt ?? getDateFormat(), true, getDisplayTimezone());
}

export function formatChartCursor(unixSec: number, fmt?: DateDisplayFormat): string {
  const d = toDate(unixSec * 1000);
  if (!d) return "";
  return formatWithMode(d, fmt ?? getDateFormat(), true, getDisplayTimezone());
}

function formatTimeHm(date: Date, timeZone?: string): string {
  const p = partsInTimezone(date, timeZone);
  return `${pad2(p.hour)}:${pad2(p.minute)}`;
}

function localDayKey(date: Date, timeZone?: string): string {
  const p = partsInTimezone(date, timeZone);
  return `${p.year}-${p.month}-${p.day}`;
}

/** X-axis tick labels: date at axis start or day boundary; HH:mm elsewhere. */
export function formatChartAxisLabels(
  ticksSec: number[],
  fmt?: DateDisplayFormat,
): string[] {
  const mode = fmt ?? getDateFormat();
  const tz = getDisplayTimezone();
  return ticksSec.map((unixSec, i) => {
    const d = toDate(unixSec * 1000);
    if (!d) return "";
    if (i === 0) return formatWithMode(d, mode, false, tz);
    const prev = toDate(ticksSec[i - 1]! * 1000);
    if (prev && localDayKey(d, tz) !== localDayKey(prev, tz)) {
      return formatWithMode(d, mode, false, tz);
    }
    return formatTimeHm(d, tz);
  });
}
