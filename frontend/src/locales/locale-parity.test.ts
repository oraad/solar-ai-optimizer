import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { DEFAULT_LOCALE, LOCALES, LOCALE_LOADERS } from "./manifest.js";

const root = dirname(fileURLToPath(import.meta.url));

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
  const en = JSON.parse(readFileSync(join(root, "en.json"), "utf8"));
  const enKeys = new Set(leafKeys(en));

  it("every manifest locale has a loader", () => {
    for (const loc of LOCALES) {
      expect(LOCALE_LOADERS[loc.id as keyof typeof LOCALE_LOADERS]).toBeTypeOf("function");
    }
  });

  for (const loc of LOCALES) {
    if (loc.id === DEFAULT_LOCALE) continue;
    it(`${loc.id}.json has same keys as en.json`, () => {
      const data = JSON.parse(readFileSync(join(root, `${loc.id}.json`), "utf8"));
      const keys = new Set(leafKeys(data));
      expect(keys).toEqual(enKeys);
    });
  }
});
