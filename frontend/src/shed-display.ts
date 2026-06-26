import type { ShedAction, ShedResult } from "./types.js";

export interface TierShedActionSummary {
  tier: string;
  desired_on: boolean;
  reason: string;
  entities: string[];
}

export interface TierShedResultSummary {
  tier: string;
  desired_on: boolean;
  entities: string[];
  allVerified: boolean;
  uniformSkipReason: string | null;
  uniformSkipReasonText: string | null;
  hasPartialFailure: boolean;
  primarySkipReason: string | null;
  primarySkipReasonText: string | null;
  wasOffBeforeShed: boolean;
  companionsRestored: string[];
  results: ShedResult[];
}

function groupByTier<T extends { tier: string }>(
  items: T[],
): Map<string, T[]> {
  const order: string[] = [];
  const groups = new Map<string, T[]>();
  for (const item of items) {
    if (!groups.has(item.tier)) {
      order.push(item.tier);
      groups.set(item.tier, []);
    }
    groups.get(item.tier)!.push(item);
  }
  return new Map(order.map((tier) => [tier, groups.get(tier)!]));
}

export function groupShedActionsByTier(actions: ShedAction[]): TierShedActionSummary[] {
  const groups = groupByTier(actions);
  return [...groups.entries()].map(([, group]) => {
    const first = group[0];
    return {
      tier: first.tier,
      desired_on: first.desired_on,
      reason: first.reason,
      entities: group.map((a) => a.entity),
    };
  });
}

function skipKey(r: ShedResult): string | null {
  if (r.error) return `error:${r.error}`;
  if (r.skipped_reason) return `skip:${r.skipped_reason}`;
  return null;
}

function entityStatusLabel(r: ShedResult): string {
  if (r.verified) return "ok";
  if (r.error) return r.error;
  if (r.skipped_reason_text) return r.skipped_reason_text;
  if (r.skipped_reason) return r.skipped_reason;
  return "pending";
}

export function shedActionTooltip(summary: TierShedActionSummary, onLabel: string, shedLabel: string): string {
  const state = summary.desired_on ? onLabel : shedLabel;
  const lines = summary.entities.map((e) => `${e}: ${state}`);
  return [summary.reason, ...lines].join("\n");
}

export function shedResultTooltip(summary: TierShedResultSummary): string {
  return summary.results
    .map((r) => {
      const state = r.desired_on ? "on" : "off";
      return `${r.entity}: ${state} ${entityStatusLabel(r)}`;
    })
    .join("\n");
}

function firstNonVerifiedResult(group: ShedResult[]): ShedResult | undefined {
  return group.find((r) => !r.verified);
}

export function groupShedResultsByTier(results: ShedResult[]): TierShedResultSummary[] {
  const groups = groupByTier(results);
  return [...groups.entries()].map(([, group]) => {
    const first = group[0];
    const allVerified = group.every((r) => r.verified);
    const skipKeys = group.map(skipKey);
    const nonNullKeys = skipKeys.filter((k): k is string => k !== null);
    const uniformSkip =
      nonNullKeys.length === group.length && new Set(nonNullKeys).size === 1;
    const primary = firstNonVerifiedResult(group);
    const companionsRestored = [
      ...new Set(group.flatMap((r) => r.companions_restored ?? [])),
    ];
    const uniformResult = uniformSkip ? group[0] : null;

    return {
      tier: first.tier,
      desired_on: first.desired_on,
      entities: group.map((r) => r.entity),
      allVerified,
      uniformSkipReason: uniformResult?.skipped_reason ?? null,
      uniformSkipReasonText:
        uniformResult?.skipped_reason_text ??
        uniformResult?.error ??
        uniformResult?.skipped_reason ??
        null,
      hasPartialFailure: !allVerified && !uniformSkip,
      primarySkipReason: primary?.skipped_reason ?? null,
      primarySkipReasonText:
        primary?.skipped_reason_text ?? primary?.error ?? primary?.skipped_reason ?? null,
      wasOffBeforeShed: group.some(
        (r) => r.skipped_reason === "engine.skip.was_off_before_shed",
      ),
      companionsRestored,
      results: group,
    };
  });
}
