export type LocaleMeta = {
  id: string;
  nativeName: string;
  dir: "ltr" | "rtl";
  match?: string[];
};

export const DEFAULT_LOCALE = "en" as const;

export const LOCALES: readonly LocaleMeta[] = [
  { id: "en", nativeName: "English", dir: "ltr", match: ["en"] },
  { id: "ar", nativeName: "العربية", dir: "rtl", match: ["ar"] },
  { id: "fr", nativeName: "Français", dir: "ltr", match: ["fr"] },
] as const;

export type AppLocale = (typeof LOCALES)[number]["id"];

export const SUPPORTED_LOCALE_IDS: AppLocale[] = LOCALES.map((l) => l.id as AppLocale);

export type Messages = Record<string, unknown>;

export const LOCALE_LOADERS: Record<
  AppLocale,
  () => Promise<{ default: Messages }>
> = {
  en: () => import("./en.json"),
  ar: () => import("./ar.json"),
  fr: () => import("./fr.json"),
};

/** Inline map for index.html boot script (id → dir). Keep in sync with LOCALES. */
export const LOCALE_DIR_INLINE: Record<string, "ltr" | "rtl"> = Object.fromEntries(
  LOCALES.map((l) => [l.id, l.dir]),
);

export function localeMeta(id: string): LocaleMeta | undefined {
  return LOCALES.find((l) => l.id === id);
}

export function isSupportedLocale(id: string): id is AppLocale {
  return SUPPORTED_LOCALE_IDS.includes(id as AppLocale);
}

export function resolveBrowserLocale(): AppLocale {
  if (typeof navigator === "undefined") return DEFAULT_LOCALE;
  const langs = navigator.languages?.length ? navigator.languages : [navigator.language];
  for (const lang of langs) {
    const base = lang.toLowerCase().split("-")[0]!;
    for (const meta of LOCALES) {
      const prefixes = meta.match ?? [meta.id];
      if (prefixes.some((p) => lang.toLowerCase() === p.toLowerCase() || base === p.toLowerCase())) {
        return meta.id as AppLocale;
      }
    }
  }
  return DEFAULT_LOCALE;
}
