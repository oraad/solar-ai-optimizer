export type DateDisplayFormat = "locale" | "ddmmyy" | "iso";

const STORAGE_KEY = "solar-date-format";
const VALID: DateDisplayFormat[] = ["locale", "ddmmyy", "iso"];

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

function formatDdmmyy(date: Date, includeTime: boolean): string {
  const dd = pad2(date.getDate());
  const mm = pad2(date.getMonth() + 1);
  const yy = pad2(date.getFullYear() % 100);
  if (!includeTime) return `${dd}/${mm}/${yy}`;
  return `${dd}/${mm}/${yy} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function formatIso(date: Date, includeTime: boolean): string {
  const y = date.getFullYear();
  const m = pad2(date.getMonth() + 1);
  const d = pad2(date.getDate());
  if (!includeTime) return `${y}-${m}-${d}`;
  return `${y}-${m}-${d} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function formatLocale(date: Date, includeTime: boolean): string {
  if (includeTime) {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "short",
      timeStyle: "short",
    }).format(date);
  }
  return new Intl.DateTimeFormat(undefined, { dateStyle: "short" }).format(date);
}

function formatWithMode(
  date: Date,
  fmt: DateDisplayFormat,
  includeTime: boolean,
): string {
  switch (fmt) {
    case "ddmmyy":
      return formatDdmmyy(date, includeTime);
    case "iso":
      return formatIso(date, includeTime);
    default:
      return formatLocale(date, includeTime);
  }
}

export function formatDateTime(
  input: Date | string | number,
  fmt?: DateDisplayFormat,
): string {
  const d = toDate(input);
  if (!d) return String(input);
  return formatWithMode(d, fmt ?? getDateFormat(), true);
}

export function formatChartCursor(unixSec: number, fmt?: DateDisplayFormat): string {
  const d = toDate(unixSec * 1000);
  if (!d) return "";
  return formatWithMode(d, fmt ?? getDateFormat(), true);
}

export function formatChartAxis(
  unixSec: number,
  fmt?: DateDisplayFormat,
  spanSec?: number,
): string {
  const d = toDate(unixSec * 1000);
  if (!d) return "";
  const includeTime = spanSec == null ? true : spanSec <= 86400;
  return formatWithMode(d, fmt ?? getDateFormat(), includeTime);
}
