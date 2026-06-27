/** Pure helpers for load-shedding tier editing and validation. */

export function tierSwitches(t: Record<string, unknown>): string[] {
  if (Array.isArray(t.switches)) {
    const list = t.switches.map((s) => String(s ?? ""));
    return list.length ? list : [""];
  }
  const legacy = String(t.switch ?? "").trim();
  return legacy ? [legacy] : [""];
}

export function tierDeviceCount(t: Record<string, unknown>): number {
  return tierSwitches(t)
    .map((s) => s.trim())
    .filter(Boolean).length;
}

export function stateEntitiesMap(t: Record<string, unknown>): Record<string, string[]> {
  const raw = t.state_entities;
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const out: Record<string, string[]> = {};
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (Array.isArray(v)) out[k] = v.map(String);
  }
  return out;
}

export function validateLoadSheddingTiers(
  draft: Record<string, unknown> | null,
  msg: (key: string, params?: Record<string, string>) => string,
): string | null {
  const tiers = (draft?.tiers ?? []) as Record<string, unknown>[];
  for (let i = 0; i < tiers.length; i++) {
    const tier = tiers[i]!;
    const name = String(tier.name ?? "").trim();
    const entities = tierSwitches(tier).map((s) => s.trim()).filter(Boolean);
    if (!name) return msg("ui.loadShedding.validationTierName", { n: String(i + 1) });
    if (!entities.length) {
      return msg("ui.loadShedding.validationTierEntities", { name });
    }
  }
  return null;
}

export function normalizeTiersForSave(d: Record<string, unknown>): void {
  const tiers = (d.tiers ?? []) as Record<string, unknown>[];
  d.tiers = tiers.map((t) => {
    const switches = tierSwitches(t).map((s) => s.trim()).filter(Boolean);
    const { switch: _legacy, ...rest } = t as Record<string, unknown> & { switch?: string };
    return { ...rest, switches };
  });
}
