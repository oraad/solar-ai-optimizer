/** Format minutes as a short human duration (e.g. 45m, 2h 15m, >24h). */

const MAX_MINUTES = 24 * 60;

export function formatDuration(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes < 0) return "";
  if (minutes > MAX_MINUTES) return ">24h";
  const m = Math.round(minutes);
  if (m < 2) return "";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const rem = m % 60;
  return rem ? `${h}h ${rem}m` : `${h}h`;
}

export interface BatteryEtaInput {
  soc: number | null;
  powerW: number | null;
  capacityKwh: number;
  roundTripEfficiency: number;
  maxSocCeiling: number;
  minSocFloor: number;
  targetSoc: number | null;
  autonomyFloorSoc: number | null;
}

const POWER_IDLE_W = 20;

export function batteryEtaLine(input: BatteryEtaInput): string | null {
  const {
    soc,
    powerW,
    capacityKwh,
    roundTripEfficiency,
    maxSocCeiling,
    minSocFloor,
    targetSoc,
    autonomyFloorSoc,
  } = input;

  if (soc == null || powerW == null || capacityKwh <= 0) return null;

  const usableWh = capacityKwh * 1000;
  const eff = Math.max(0.1, roundTripEfficiency || 0.9);
  const power = Math.max(Math.abs(powerW), POWER_IDLE_W);

  if (powerW > POWER_IDLE_W) {
    const chargeTarget =
      targetSoc != null ? Math.min(targetSoc, maxSocCeiling) : maxSocCeiling;
    const delta = chargeTarget - soc;
    if (delta <= 0.5) return null;
    const wh = (delta / 100) * usableWh / eff;
    const minutes = (wh / power) * 60;
    const fmt = formatDuration(minutes);
    return fmt ? `Full in ~${fmt}` : null;
  }

  if (powerW < -POWER_IDLE_W) {
    const floor = autonomyFloorSoc ?? minSocFloor;
    const delta = soc - floor;
    if (delta <= 0.5) return null;
    const wh = (delta / 100) * usableWh;
    const minutes = (wh / power) * 60;
    const fmt = formatDuration(minutes);
    return fmt ? `Reserve in ~${fmt}` : null;
  }

  return null;
}
