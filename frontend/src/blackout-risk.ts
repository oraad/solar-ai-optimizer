import { t } from "./i18n.js";
import type { BlackoutRisk } from "./types.js";

export type RiskPillClass = "good" | "warn" | "bad" | "critical" | "muted";

export function riskPillClassFromScore(score: number): RiskPillClass {
  if (score >= 0.66) return "bad";
  if (score >= 0.33) return "warn";
  return "good";
}

export function riskPillClassFromLevel(level: BlackoutRisk | string): RiskPillClass {
  switch (level) {
    case "low":
      return "good";
    case "moderate":
      return "warn";
    case "high":
      return "bad";
    case "critical":
      return "critical";
    default:
      return "muted";
  }
}

export function riskLevelLabel(level: BlackoutRisk | string): string {
  switch (level) {
    case "low":
      return t("ui.status.risk.low");
    case "moderate":
      return t("ui.status.risk.moderate");
    case "high":
      return t("ui.status.risk.high");
    case "critical":
      return t("ui.status.risk.critical");
    default:
      return String(level);
  }
}

export function riskLevelFromScore(score: number): BlackoutRisk {
  if (score >= 0.66) return "high";
  if (score >= 0.33) return "moderate";
  return "low";
}

export function formatRiskScorePct(score: number): string {
  return `${(score * 100).toFixed(0)}%`;
}

export type RiskDisplay = {
  label: string;
  pillClass: RiskPillClass;
  pct: string | null;
};

export function formatRiskFromScore(score: number): RiskDisplay {
  return {
    label: riskLevelLabel(riskLevelFromScore(score)),
    pillClass: riskPillClassFromScore(score),
    pct: formatRiskScorePct(score),
  };
}

export function formatRiskFromLevel(level: BlackoutRisk | string): RiskDisplay {
  return {
    label: riskLevelLabel(level),
    pillClass: riskPillClassFromLevel(level),
    pct: null,
  };
}

export function formatRiskFromDecision(opts: {
  score?: number | null;
  level?: BlackoutRisk | string | null;
}): RiskDisplay | null {
  if (opts.score != null) return formatRiskFromScore(opts.score);
  if (opts.level) return formatRiskFromLevel(opts.level);
  return null;
}
