/** Settings sidebar / pill navigation structure. */

export type SettingsCategory = "setup" | "energy" | "engine" | "forecast" | "safety" | "system";

export type SettingsNavId =
  | "setup_ha"
  | "setup_site"
  | "setup_inverter"
  | "energy_battery"
  | "energy_reserve"
  | "energy_grid"
  | "engine"
  | "forecast_temp"
  | "safety"
  | "system";

export interface SettingsNavItem {
  id: SettingsNavId;
  category: SettingsCategory;
  /** i18n key under ui.settings.nav.* or settings.sections.* */
  labelKey: string;
}

export const SETTINGS_CATEGORIES: SettingsCategory[] = [
  "setup",
  "energy",
  "engine",
  "forecast",
  "safety",
  "system",
];

export const SETTINGS_NAV: SettingsNavItem[] = [
  { id: "setup_ha", category: "setup", labelKey: "ui.settings.nav.connection" },
  { id: "setup_site", category: "setup", labelKey: "ui.settings.nav.sitePv" },
  { id: "setup_inverter", category: "setup", labelKey: "ui.settings.nav.inverter" },
  { id: "energy_battery", category: "energy", labelKey: "settings.sections.battery" },
  { id: "energy_reserve", category: "energy", labelKey: "settings.sections.reserve" },
  { id: "energy_grid", category: "energy", labelKey: "settings.sections.grid_charge" },
  { id: "engine", category: "engine", labelKey: "settings.sections.engine" },
  { id: "forecast_temp", category: "forecast", labelKey: "ui.settings.nav.temperature" },
  { id: "safety", category: "safety", labelKey: "ui.settings.nav.safety" },
  { id: "system", category: "system", labelKey: "ui.settings.nav.system" },
];

export function navItemsForCategory(category: SettingsCategory): SettingsNavItem[] {
  return SETTINGS_NAV.filter((n) => n.category === category);
}

export function categoryForNav(id: SettingsNavId): SettingsCategory {
  return SETTINGS_NAV.find((n) => n.id === id)?.category ?? "setup";
}
