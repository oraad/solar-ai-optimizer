import {
  DEFAULT_LOCALE,
  LOCALE_LOADERS,
  type AppLocale,
  type Messages,
  isSupportedLocale,
  localeMeta,
  resolveBrowserLocale,
} from "./locales/manifest.js";
import enBundled from "./locales/en.json";

export {
  DEFAULT_LOCALE,
  LOCALES,
  LOCALE_DIR_INLINE,
  resolveBrowserLocale,
  type AppLocale,
} from "./locales/manifest.js";

const STORAGE_KEY = "solar-locale";
export const LOCALE_CHANGE_EVENT = "solar-locale-change";

let activeLocale: AppLocale = DEFAULT_LOCALE;
let enMessages: Messages = enBundled as Messages;
let activeMessages: Messages = enMessages;
let initPromise: Promise<void> | null = null;

function readStoredLocale(): AppLocale | null {
  if (typeof localStorage === "undefined") return null;
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v && isSupportedLocale(v)) return v;
  } catch {
    /* ignore */
  }
  return null;
}

function persistLocale(locale: AppLocale): void {
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    /* ignore */
  }
}

function applyDocumentLocale(locale: AppLocale): void {
  if (typeof document === "undefined") return;
  const meta = localeMeta(locale);
  document.documentElement.lang = locale;
  document.documentElement.dir = meta?.dir ?? "ltr";
}

function getNested(obj: Messages, key: string): string | undefined {
  const parts = key.split(".");
  let cur: unknown = obj;
  for (const part of parts) {
    if (cur == null || typeof cur !== "object") return undefined;
    cur = (cur as Record<string, unknown>)[part];
  }
  return typeof cur === "string" ? cur : undefined;
}

function interpolate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (_, name: string) => {
    const v = params[name];
    return v == null ? `{${name}}` : String(v);
  });
}

async function loadMessages(locale: AppLocale): Promise<Messages> {
  const mod = await LOCALE_LOADERS[locale]();
  return mod.default;
}

export function getLocale(): AppLocale {
  return activeLocale;
}

export function getTextDirection(locale: AppLocale = activeLocale): "ltr" | "rtl" {
  return localeMeta(locale)?.dir ?? "ltr";
}

export function t(
  key: string,
  params?: Record<string, string | number>,
  fallback?: string,
): string {
  const raw =
    getNested(activeMessages, key) ??
    getNested(enMessages, key) ??
    fallback ??
    key;
  return interpolate(raw, params);
}

export async function initI18n(): Promise<void> {
  if (initPromise) return initPromise;
  initPromise = (async () => {
    const stored = readStoredLocale();
    const initial = stored ?? resolveBrowserLocale();
    await setLocale(initial, { skipPersist: !!stored });
  })();
  return initPromise;
}

export async function setLocale(
  locale: AppLocale,
  opts?: { skipPersist?: boolean },
): Promise<void> {
  const resolved = isSupportedLocale(locale) ? locale : DEFAULT_LOCALE;
  if (resolved !== DEFAULT_LOCALE) {
    activeMessages = await loadMessages(resolved);
  } else {
    activeMessages = enMessages;
    if (!Object.keys(enMessages).length) {
      enMessages = await loadMessages(DEFAULT_LOCALE);
      activeMessages = enMessages;
    }
  }
  activeLocale = resolved;
  if (!opts?.skipPersist) persistLocale(resolved);
  applyDocumentLocale(resolved);
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(LOCALE_CHANGE_EVENT));
  }
}
