/**
 * Builds en.json from legacy field-labels.ts and field-help.ts string maps.
 * Run: npx tsx scripts/generate-en-catalog.mts
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "src");

function extractBlock(src: string, varName: string): string {
  const start = src.indexOf(`const ${varName}`);
  if (start < 0) throw new Error(`Block ${varName} not found`);
  const brace = src.indexOf("{", start);
  let depth = 0;
  for (let i = brace; i < src.length; i++) {
    if (src[i] === "{") depth++;
    else if (src[i] === "}") {
      depth--;
      if (depth === 0) return src.slice(brace + 1, i);
    }
  }
  throw new Error(`Unclosed block ${varName}`);
}

function parseStringEntries(body: string): Record<string, string> {
  const out: Record<string, string> = {};
  const re = /(\w+):\s*(?:"((?:\\.|[^"\\])*)"|'((?:\\.|[^'\\])*)')/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(body)) !== null) {
    out[m[1]!] = (m[2] ?? m[3] ?? "").replace(/\\n/g, "\n");
  }
  return out;
}

function parseNestedStrings(body: string): Record<string, Record<string, string>> {
  const out: Record<string, Record<string, string>> = {};
  const sectionRe = /(\w+):\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}/g;
  let sm: RegExpExecArray | null;
  while ((sm = sectionRe.exec(body)) !== null) {
    out[sm[1]!] = parseStringEntries(sm[2]!);
  }
  return out;
}

function main() {
  const labels = readFileSync(join(root, "field-labels.ts"), "utf8");
  const help = readFileSync(join(root, "field-help.ts"), "utf8");

  const SECTION_TITLES = parseStringEntries(extractBlock(labels, "SECTION_TITLES"));
  const FIELD_LABELS = parseNestedStrings(extractBlock(labels, "FIELD_LABELS"));
  const ENTITY_LABELS = parseStringEntries(extractBlock(labels, "ENTITY_LABELS"));
  const OPTIMIZATION_PRIORITY_LABELS = parseStringEntries(
    extractBlock(labels, "OPTIMIZATION_PRIORITY_LABELS"),
  );
  const CAPABILITY_LABELS = parseStringEntries(extractBlock(labels, "CAPABILITY_LABELS"));

  const FIELD_HELP = parseNestedStrings(extractBlock(help, "FIELD_HELP"));
  const ENTITY_HELP = parseStringEntries(extractBlock(help, "ENTITY_HELP"));
  const PRIORITY_EFFECT_HELP = parseStringEntries(extractBlock(help, "PRIORITY_EFFECT_HELP"));
  const PRIORITY_RANK_BLURBS = parseStringEntries(extractBlock(help, "PRIORITY_RANK_BLURBS"));
  const OVERRIDE_HELP = parseStringEntries(extractBlock(help, "OVERRIDE_HELP"));
  const ASSISTANT_HELP = parseStringEntries(extractBlock(help, "ASSISTANT_HELP"));
  const STATUS_HELP = parseStringEntries(extractBlock(help, "STATUS_HELP"));
  const sectionHelpHints = parseStringEntries(
    help.match(/const hints: Record<string, string> = \{([\s\S]*?)\n  \};/)?.[1] ?? "",
  );

  const catalog = {
    app: {
      title: "Solar AI Optimizer",
      bootSub: "Verifying access…",
      bootAria: "Loading Solar AI Optimizer",
    },
    nav: {
      overview: "Overview",
      forecast: "Forecast",
      history: "History",
      assistant: "Assistant",
      load_shedding: "Load shedding",
      settings: "Settings",
      shedding: "Shedding",
      chat: "Chat",
    },
    display: {
      preferences: "Display preferences",
      preferencesIntro:
        "How dates and times appear in history tables and charts on this browser.",
      language: "Language",
      dateFormat: "Date format",
      dateLocale: "Locale (browser default)",
      dateDdmmyy: "DD/MM/YY",
      dateIso: "YYYY-MM-DD (ISO)",
    },
    settings: {
      sections: SECTION_TITLES,
      fields: FIELD_LABELS,
      entities: ENTITY_LABELS,
      capabilities: CAPABILITY_LABELS,
      priorities: OPTIMIZATION_PRIORITY_LABELS,
    },
    help: {
      fields: FIELD_HELP,
      entities: ENTITY_HELP,
      priorities: PRIORITY_EFFECT_HELP,
      priorityBlurbs: PRIORITY_RANK_BLURBS,
      overrides: OVERRIDE_HELP,
      assistant: ASSISTANT_HELP,
      status: STATUS_HELP,
      sections: sectionHelpHints,
      sectionFallback: "Settings for {section}.",
    },
    update: {
      stages: {
        starting: "Preparing update…",
        backing_up: "Backing up data…",
        pulling: "Pulling container image…",
        stopping: "Stopping current container…",
        restoring_data: "Restoring backup data…",
        recreating: "Starting updated container…",
        verifying: "Verifying service health…",
        finishing: "Finalizing…",
        failed: "Update failed",
      },
      chipUpdating: "UPDATING…",
      chipPrefix: "UPDATING: {label}",
      restarting: "Restarting service…",
      updatingVersion: "Updating v{from} → v{to}",
      restoreInProgress: "Restore in progress",
      updateInProgress: "Update in progress",
      logHint: "Details: data volume `.update-logs/latest.log`",
    },
    duration: {
      over24h: ">24h",
      minutes: "{m}m",
      hours: "{h}h",
      hoursMinutes: "{h}h {m}m",
      fullIn: "Full in ~{duration}",
      reserveIn: "Reserve in ~{duration}",
    },
    toast: {
      errorPrefix: "Error: {message}",
    },
    login: {
      sub: "Sign in with your local admin account.",
      username: "Username",
      password: "Password",
      placeholder: "admin",
      signingIn: "Signing in…",
      signIn: "Sign in",
      toastLoading: "Signing in…",
      toastSuccess: "Signed in.",
    },
    common: {
      off: "OFF",
      on: "ON",
      loading: "Loading…",
      save: "Save changes",
      cancel: "Cancel",
      present: "present",
      absent: "absent",
      unknown: "unknown",
      never: "never",
      charging: "charging",
      discharging: "discharging",
      idle: "idle",
      device: "device",
      devices: "devices",
      auto: "auto",
    },
  };

  const outPath = join(root, "locales", "en.json");
  writeFileSync(outPath, JSON.stringify(catalog, null, 2) + "\n", "utf8");
  console.log("Wrote", outPath);
}

main();
