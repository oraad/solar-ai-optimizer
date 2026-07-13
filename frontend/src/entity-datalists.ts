import type { EntityInfo } from "./types.js";

export const SHED_ENTITY_DOMAINS = ["switch", "input_boolean"] as const;

/** Stable array reference for Lit property binding in load-shedding tier inputs. */
export const SHED_DOMAINS: string[] = ["switch", "input_boolean"];

/** Empty `domains` matches no entities. */
export function filterEntitiesByDomains(
  entities: EntityInfo[],
  domains: readonly string[],
): EntityInfo[] {
  if (!domains.length) return [];
  return entities.filter((e) => domains.includes(e.domain));
}

export function hasEntitiesForDomains(
  entities: EntityInfo[],
  domains: readonly string[],
): boolean {
  return filterEntitiesByDomains(entities, domains).length > 0;
}
