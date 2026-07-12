/** Short help text for settings fields, entities, and control actions. */

import { t } from "./i18n.js";

function titleCaseSnake(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function fieldHelp(section: string, key: string): string | undefined {
  const v = t(`help.fields.${section}.${key}`);
  return v === `help.fields.${section}.${key}` ? undefined : v;
}

export function priorityEffectHelp(key: string): string | undefined {
  const v = t(`help.priorities.${key}`);
  return v === `help.priorities.${key}` ? undefined : v;
}

export function priorityRankBlurb(key: string): string {
  const v = t(`help.priorityBlurbs.${key}`);
  return v === `help.priorityBlurbs.${key}` ? "" : v;
}

export function entityHelp(key: string): string | undefined {
  const v = t(`help.entities.${key}`);
  return v === `help.entities.${key}` ? undefined : v;
}

export function pvHelp(key: string): string | undefined {
  return fieldHelp("pv", key);
}

export function overrideHelp(key: string): string | undefined {
  const v = t(`help.overrides.${key}`);
  return v === `help.overrides.${key}` ? undefined : v;
}

export function statusHelp(key: string): string | undefined {
  const v = t(`help.status.${key}`);
  return v === `help.status.${key}` ? undefined : v;
}

export function sectionHelp(section: string): string | undefined {
  const v = t(`help.sections.${section}`);
  if (v !== `help.sections.${section}`) return v;
  return t("help.sectionFallback", { section: titleCaseSnake(section) });
}
