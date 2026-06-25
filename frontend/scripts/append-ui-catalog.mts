/**
 * Merges ui-catalog.json into locales/en.json under the "ui" key.
 * Run: npx tsx scripts/append-ui-catalog.mts
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "locales");
const en = JSON.parse(readFileSync(join(root, "en.json"), "utf8"));
const ui = JSON.parse(readFileSync(join(root, "ui-catalog.json"), "utf8"));
en.ui = ui;
writeFileSync(join(root, "en.json"), JSON.stringify(en, null, 2) + "\n", "utf8");
console.log("Merged ui-catalog into en.json");
