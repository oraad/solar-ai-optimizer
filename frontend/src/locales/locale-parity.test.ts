import { describe, expect, it } from "vitest";

import { DEFAULT_LOCALE, LOCALES, LOCALE_LOADERS } from "./manifest.js";

function leafKeys(obj: unknown, prefix = ""): string[] {
  if (obj == null || typeof obj !== "object") return [];
  if (Array.isArray(obj)) return [];
  const out: string[] = [];
  for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v != null && typeof v === "object" && !Array.isArray(v)) {
      out.push(...leafKeys(v, path));
    } else {
      out.push(path);
    }
  }
  return out;
}

describe("locale catalogs", () => {
  it("every manifest locale has a loader", () => {
    for (const loc of LOCALES) {
      expect(LOCALE_LOADERS[loc.id as keyof typeof LOCALE_LOADERS]).toBeTypeOf("function");
    }
  });

  it("non-en locales have same keys as en.json", async () => {
    const en = (await LOCALE_LOADERS.en()).default;
    const enKeys = new Set(leafKeys(en));

    for (const loc of LOCALES) {
      if (loc.id === DEFAULT_LOCALE) continue;
      const data = (await LOCALE_LOADERS[loc.id as keyof typeof LOCALE_LOADERS]()).default;
      const keys = new Set(leafKeys(data));
      expect(keys, loc.id).toEqual(enKeys);
    }
  });
});
