/** Human-readable labels for Settings fields (display only; keys unchanged in API). */

import { t } from "./i18n.js";

function titleCaseSnake(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function sectionTitle(section: string): string {
  return t(`settings.sections.${section}`, undefined, titleCaseSnake(section));
}

export function fieldLabel(section: string, key: string): string {
  return t(`settings.fields.${section}.${key}`, undefined, titleCaseSnake(key));
}

export function entityLabel(key: string): string {
  return t(`settings.entities.${key}`, undefined, titleCaseSnake(key));
}

export function capabilityLabel(key: string): string {
  return t(`settings.capabilities.${key}`, undefined, entityLabel(key));
}

export function optimizationPriorityLabel(key: string): string {
  return t(`settings.priorities.${key}`, undefined, titleCaseSnake(key));
}

export function pvLabel(key: string): string {
  return t(`settings.fields.pv.${key}`, undefined, titleCaseSnake(key));
}

/** Read-map entity keys rendered in Settings (excludes non-entity flags). */
export const INVERTER_READ_ENTITY_KEYS = [
  "pv_power",
  "load_power",
  "battery_soc",
  "battery_power",
  "grid_power",
  "grid_present",
  "battery_temp",
] as const;
