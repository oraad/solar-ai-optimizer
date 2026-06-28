import { t } from "./i18n.js";
import type { GridChargePlan } from "./types.js";

/** Primary amps label for Decision panel stat (unchanged semantics). */
export function gridChargeLabel(gc: GridChargePlan | null | undefined): string {
  if (!gc) return "--";
  if (gc.enabled && gc.target_amps > 0) return `${gc.target_amps.toFixed(0)} A`;
  return t("common.off");
}

export type GridChargeSubline = { text: string; color: string };

/** Charge subline for Live status Grid tile. Returns null when grid charge subsystem is disabled. */
export function gridChargeSubline(
  gc: GridChargePlan | null | undefined,
  gridAbsent: boolean,
  gridChargeEnabled: boolean,
): GridChargeSubline | null {
  if (!gridChargeEnabled) return null;
  if (!gc) return { text: "--", color: "var(--muted)" };

  const charging = !gridAbsent && gc.enabled && gc.target_amps > 0;
  if (charging) {
    return {
      text: t("ui.status.gridChargeLine", {
        current: gc.target_amps.toFixed(0),
        max: gc.max_amps.toFixed(0),
      }),
      color: "var(--good)",
    };
  }

  return {
    text: t("ui.status.gridChargeOffMax", { max: gc.max_amps.toFixed(0) }),
    color: "var(--muted)",
  };
}
