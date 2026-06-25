import { beforeEach, describe, expect, it, vi } from "vitest";

import { LOCALE_CHANGE_EVENT, getLocale, getTextDirection, initI18n, setLocale, t } from "./i18n.js";

describe("i18n", () => {
  beforeEach(async () => {
    localStorage.clear();
    document.documentElement.lang = "en";
    document.documentElement.dir = "ltr";
    await initI18n();
    await setLocale("en");
  });

  it("returns English by default", () => {
    expect(t("nav.overview")).toBe("Overview");
    expect(getLocale()).toBe("en");
  });

  it("resolves French strings after setLocale", async () => {
    await setLocale("fr");
    expect(getLocale()).toBe("fr");
    expect(t("nav.overview")).toBe("Aperçu");
  });

  it("sets rtl for Arabic", async () => {
    await setLocale("ar");
    expect(getTextDirection()).toBe("rtl");
    expect(document.documentElement.dir).toBe("rtl");
    expect(document.documentElement.lang).toBe("ar");
  });

  it("falls back to English for missing keys", async () => {
    await setLocale("fr");
    const key = "nonexistent.deep.key";
    expect(t(key)).toBe(key);
  });

  it("interpolates parameters", () => {
    expect(t("duration.minutes", { m: 15 })).toBe("15m");
  });

  it("dispatches solar-locale-change on switch", async () => {
    const spy = vi.fn();
    window.addEventListener(LOCALE_CHANGE_EVENT, spy);
    await setLocale("fr");
    expect(spy).toHaveBeenCalled();
    window.removeEventListener(LOCALE_CHANGE_EVENT, spy);
  });
});
