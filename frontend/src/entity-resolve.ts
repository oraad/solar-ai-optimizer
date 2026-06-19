import type { EntityInfo } from "./types.js";

const ENTITY_ID_RE = /^[a-z_]+\.[a-z0-9_]+$/i;

export function entityDisplayName(
  entityId: string | null | undefined,
  entities: EntityInfo[],
): string {
  if (!entityId) return "";
  const hit = entities.find((e) => e.entity_id === entityId);
  return hit?.name ?? entityId;
}

export function resolveEntity(
  text: string,
  entities: EntityInfo[],
  domains?: string[],
): string | null {
  const trimmed = text.trim();
  if (!trimmed) return null;

  const pool = domains?.length
    ? entities.filter((e) => domains.includes(e.domain))
    : entities;

  const byId = pool.find((e) => e.entity_id === trimmed);
  if (byId) return byId.entity_id;

  if (ENTITY_ID_RE.test(trimmed)) return trimmed;

  const lower = trimmed.toLowerCase();
  const byName = pool.filter((e) => e.name.toLowerCase() === lower);
  if (byName.length === 1) return byName[0]!.entity_id;
  return null;
}
