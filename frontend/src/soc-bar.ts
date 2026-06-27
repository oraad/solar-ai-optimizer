function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

function socGradientStops(min: number): string {
  if (min <= 0) return "var(--accent) 0%,var(--good) 100%";
  if (min >= 100) return "var(--bad) 0%,var(--accent) 100%";
  return `var(--bad) 0%,var(--accent) ${min}%,var(--good) 100%`;
}

/** Inline CSS for a battery SoC fill: blended bad→accent→good ramp anchored at min floor. */
export function socFillStyle(soc: number | null, minSocFloor: number): string {
  const pct = clamp(soc ?? 0, 0, 100);
  const min = clamp(minSocFloor, 0, 100);
  if (pct <= 0) return "width:0%";
  const bgSize = (100 / pct) * 100;
  return [
    `width:${pct}%`,
    `background:linear-gradient(90deg,${socGradientStops(min)})`,
    `background-size:${bgSize}% 100%`,
    "background-repeat:no-repeat",
  ].join(";");
}
