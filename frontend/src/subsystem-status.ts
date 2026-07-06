import { t } from "./i18n.js";
import type { SystemStatus } from "./types.js";

export type StatusAlert = {
  label: string;
  className: string;
  title?: string;
  onClick?: () => void;
};

/** Top-bar pills for shedding / grid charge / optimization enable and pause state. */
export function buildSubsystemAlerts(status: SystemStatus | null): StatusAlert[] {
  if (!status) return [];
  const pills: StatusAlert[] = [];
  if (status.shedding_enabled) {
    if (status.force_shed_off_override === true) {
      pills.push({
        label: t("ui.app.shedForced"),
        className: "warn",
      });
    } else {
      pills.push({
        label: status.paused_shedding ? t("ui.app.shedPaused") : t("ui.app.shedOn"),
        className: status.paused_shedding ? "warn" : "good",
      });
    }
  } else {
    pills.push({ label: t("ui.app.shedOff"), className: "warn" });
  }
  if (status.grid_charge_enabled !== false) {
    if (status.force_grid_charge_override === true) {
      pills.push({
        label: t("ui.app.gridForced"),
        className: "warn",
      });
    } else {
      pills.push({
        label: status.paused_grid_charge ? t("ui.app.gridPaused") : t("ui.app.gridOn"),
        className: status.paused_grid_charge ? "warn" : "good",
      });
    }
  } else {
    pills.push({ label: t("ui.app.gridOff"), className: "warn" });
  }
  if (status.engine_enabled !== false) {
    pills.push({
      label: status.paused_optimization ? t("ui.app.optPaused") : t("ui.app.optOn"),
      className: status.paused_optimization ? "warn" : "good",
    });
  } else {
    pills.push({ label: t("ui.app.optOff"), className: "warn" });
  }
  return pills;
}
