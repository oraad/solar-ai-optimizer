import { html, type TemplateResult } from "lit";

import type { EntityInfo } from "./types.js";

export const SHED_ENTITY_DOMAINS = ["switch", "input_boolean"] as const;

export const SHED_DATALIST_ID = entityDatalistId("shed");

export function entityDatalistId(key: string): string {
  return `dl-${key}`;
}

/** Empty `domains` matches no entities (listId stays unset until domains are known). */
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

export function renderEntityDatalist(
  entities: EntityInfo[],
  id: string,
  domains?: readonly string[],
): TemplateResult {
  const opts = domains ? filterEntitiesByDomains(entities, domains) : entities;
  return html`<datalist id=${id}>
    ${opts.map((e) => html`<option value=${e.entity_id}>${e.name}</option>`)}
  </datalist>`;
}

export interface EntityDatalistSpec {
  id: string;
  domains?: readonly string[];
}

export function renderEntityDatalists(
  entities: EntityInfo[],
  specs: readonly EntityDatalistSpec[],
): TemplateResult {
  return html`${specs.map((s) => renderEntityDatalist(entities, s.id, s.domains))}`;
}
