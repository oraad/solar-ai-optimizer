import type { AppConfigView, SystemStatus } from "./types.js";
import type { SettingsNavId } from "./settings-nav.js";

export const SAVE_SECTIONS = [
  "site",
  "battery",
  "reserve",
  "forecast",
  "control",
  "engine",
  "inverter",
  "ha",
  "fail_safe",
  "grid_charge",
] as const;

/** Stable JSON for dirty comparison (masks ephemeral HA token field). */
export function configSnapshot(cfg: AppConfigView): string {
  const patch: Record<string, unknown> = {};
  const rec = cfg as unknown as Record<string, unknown>;
  for (const sec of SAVE_SECTIONS) {
    if (rec[sec] !== undefined) {
      const section = structuredClone(rec[sec]) as Record<string, unknown>;
      if (sec === "ha" && section) {
        section.token = "";
        delete section.has_token;
      }
      patch[sec] = section;
    }
  }
  return JSON.stringify(patch);
}

export function isConfigDirty(draft: AppConfigView | null, baseline: string): boolean {
  if (!draft || !baseline) return false;
  return configSnapshot(draft) !== baseline;
}

export interface ChecklistItem {
  id: string;
  done: boolean;
  optional?: boolean;
  labelKey: string;
  navId: SettingsNavId;
}

export function buildSetupChecklist(
  status: SystemStatus | null,
  draft: AppConfigView | null,
  entitiesConnected: boolean,
): ChecklistItem[] {
  const d = draft as unknown as Record<string, unknown> | null;
  const read = (d?.inverter as Record<string, unknown> | undefined)?.read as
    | Record<string, unknown>
    | undefined;
  const gc = d?.grid_charge as Record<string, unknown> | undefined;
  const eng = d?.engine as Record<string, unknown> | undefined;
  const ls = d?.load_shedding as Record<string, unknown> | undefined;
  const gridChargeOn = gc?.enabled !== false;
  const engineOn = eng?.enabled !== false;
  const shedPrimary = !gridChargeOn && !engineOn;
  const hasPv = Boolean(String(read?.pv_power ?? "").trim());
  const hasLoad = Boolean(String(read?.load_power ?? "").trim());
  const hasSoc = Boolean(String(read?.battery_soc ?? "").trim());
  const arrays = (d?.forecast as Record<string, unknown> | undefined)?.arrays;
  const hasArrays = Array.isArray(arrays) && arrays.length > 0;
  const locationOk = !status?.forecast_misconfigured;
  const tiers = ls?.tiers;
  const hasTiers =
    Boolean(ls?.enabled) && Array.isArray(tiers) && tiers.length > 0;
  const write = (d?.inverter as Record<string, unknown> | undefined)?.write as
    | Record<string, unknown>
    | undefined;
  const hasGridChargeWrites = Boolean(
    String(write?.grid_charge_enable ?? "").trim() ||
      String(write?.max_grid_charge_current ?? "").trim(),
  );

  const items: ChecklistItem[] = [
    {
      id: "ha",
      done: entitiesConnected || Boolean(status?.ha_connected),
      labelKey: "ui.settings.checklist.haConnected",
      navId: "setup_ha",
    },
    {
      id: "inverter",
      done: hasPv && hasLoad && hasSoc,
      labelKey: "ui.settings.checklist.inverterMapped",
      navId: "setup_inverter",
    },
    {
      id: "location",
      done: locationOk,
      optional: shedPrimary,
      labelKey: "ui.settings.checklist.siteLocation",
      navId: "setup_site",
    },
    {
      id: "pv",
      done: hasArrays,
      optional: shedPrimary,
      labelKey: "ui.settings.checklist.pvArrays",
      navId: "setup_site",
    },
    {
      id: "failsafe",
      done: Boolean(
        String((d?.fail_safe as Record<string, unknown> | undefined)?.heartbeat_entity ?? "").trim(),
      ),
      optional: true,
      labelKey: "ui.settings.checklist.failSafe",
      navId: "safety",
    },
  ];

  if (shedPrimary) {
    items.push({
      id: "shed_tiers",
      done: hasTiers,
      labelKey: "ui.settings.checklist.shedTiers",
      navId: "setup_inverter",
    });
  }

  if (gridChargeOn) {
    items.push({
      id: "grid_charge_writes",
      done: hasGridChargeWrites,
      optional: true,
      labelKey: "ui.settings.checklist.gridChargeWrites",
      navId: "setup_inverter",
    });
  }

  return items;
}

export function checklistNeedsAttention(items: ChecklistItem[]): boolean {
  return items.some((i) => !i.done && !i.optional);
}

export interface ValidationIssue {
  id: string;
  messageKey: string;
  navId?: SettingsNavId;
}

export function validateConfigDraft(draft: AppConfigView | null): ValidationIssue[] {
  if (!draft) return [];
  const issues: ValidationIssue[] = [];
  const d = draft as unknown as Record<string, unknown>;
  const gc = d.grid_charge as Record<string, unknown> | undefined;
  if (gc) {
    const maxA = Number(gc.max_grid_charge_a ?? 60);
    const minA = Number(gc.min_grid_charge_a ?? 5);
    if (Number.isFinite(maxA) && Number.isFinite(minA) && minA > maxA) {
      issues.push({
        id: "grid_charge_min_max",
        messageKey: "ui.settings.validation.gridChargeMinMax",
        navId: "energy_grid",
      });
    }
  }
  const site = d.site as Record<string, unknown> | undefined;
  if (site) {
    const lat = Number(site.latitude ?? 0);
    const lon = Number(site.longitude ?? 0);
    if (lat < -90 || lat > 90) {
      issues.push({
        id: "site_latitude",
        messageKey: "ui.settings.validation.latitude",
        navId: "setup_site",
      });
    }
    if (lon < -180 || lon > 180) {
      issues.push({
        id: "site_longitude",
        messageKey: "ui.settings.validation.longitude",
        navId: "setup_site",
      });
    }
  }
  return issues;
}

/** Match nav item or field label against search query (lowercase). */
export function matchesSettingsSearch(query: string, ...haystacks: (string | undefined)[]): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return haystacks.some((h) => h?.toLowerCase().includes(q));
}
