function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

const GREEN_SOLID_START = 85;

function socGradientStops(minFloor: number, maxCeiling: number): string {
  const min = clamp(minFloor, 0, 100);
  const max = clamp(maxCeiling, min, 100);

  if (min >= 100) return "var(--bad) 0%,var(--bad) 100%";

  const greenStart = clamp(Math.min(max, GREEN_SOLID_START), min, 100);
  const accentAt = min + (greenStart - min) / 2;

  if (min <= 0)
    return `var(--accent) 0%,var(--good) ${greenStart}%,var(--good) 100%`;

  return `var(--bad) 0%,var(--bad) ${min}%,var(--accent) ${accentAt}%,var(--good) ${greenStart}%,var(--good) 100%`;
}

/** Inline CSS for a battery SoC fill: solid red below min floor, solid green from 85% (or max ceiling when lower) to 100%, smooth accent ramp between. */
export function socFillStyle(
  soc: number | null,
  minSocFloor: number,
  maxSocCeiling: number = 100,
): string {
  const pct = clamp(soc ?? 0, 0, 100);
  const min = clamp(minSocFloor, 0, 100);
  const max = clamp(maxSocCeiling, min, 100);
  if (pct <= 0) return "width:0%";
  const bgSize = (100 / pct) * 100;
  return [
    `width:${pct}%`,
    `background:linear-gradient(90deg,${socGradientStops(min, max)})`,
    `background-size:${bgSize}% 100%`,
    "background-repeat:no-repeat",
  ].join(";");
}
