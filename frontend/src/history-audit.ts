import type { ExecutionHistoryRow, ShedExecutionRow } from "./types.js";

function executionAuditFields(row: ExecutionHistoryRow) {
  return {
    capability: row.capability,
    requested: row.requested,
    applied: row.applied,
    verified: row.verified,
    skipped_reason: row.skipped_reason,
    error: row.error,
  };
}

export function executionAuditEqual(a: ExecutionHistoryRow, b: ExecutionHistoryRow): boolean {
  const fa = executionAuditFields(a);
  const fb = executionAuditFields(b);
  return (
    fa.capability === fb.capability &&
    fa.requested === fb.requested &&
    fa.applied === fb.applied &&
    fa.verified === fb.verified &&
    fa.skipped_reason === fb.skipped_reason &&
    fa.error === fb.error
  );
}

function shedExecutionAuditFields(row: ShedExecutionRow) {
  return {
    tier: row.tier,
    entity: row.entity,
    desired_on: row.desired_on,
    applied: row.applied,
    verified: row.verified,
    skipped_reason: row.skipped_reason,
    error: row.error,
    companions_captured: row.companions_captured ?? [],
    companions_restored: row.companions_restored ?? [],
    companion_errors: row.companion_errors ?? {},
  };
}

export function shedExecutionAuditEqual(a: ShedExecutionRow, b: ShedExecutionRow): boolean {
  const fa = shedExecutionAuditFields(a);
  const fb = shedExecutionAuditFields(b);
  return (
    fa.tier === fb.tier &&
    fa.entity === fb.entity &&
    fa.desired_on === fb.desired_on &&
    fa.applied === fb.applied &&
    fa.verified === fb.verified &&
    fa.skipped_reason === fb.skipped_reason &&
    fa.error === fb.error &&
    fa.companions_captured.join() === fb.companions_captured.join() &&
    fa.companions_restored.join() === fb.companions_restored.join() &&
    JSON.stringify(fa.companion_errors) === JSON.stringify(fb.companion_errors)
  );
}

/** API returns desc by time; drop older consecutive rows with identical audit payload. */
export function dedupeConsecutiveExecutions(rows: ExecutionHistoryRow[]): ExecutionHistoryRow[] {
  if (rows.length === 0) return rows;
  const out: ExecutionHistoryRow[] = [rows[0]!];
  for (let i = 1; i < rows.length; i++) {
    const cur = rows[i]!;
    const prev = rows[i - 1]!;
    if (!executionAuditEqual(cur, prev)) {
      out.push(cur);
    }
  }
  return out;
}

export function dedupeConsecutiveShedExecutions(rows: ShedExecutionRow[]): ShedExecutionRow[] {
  if (rows.length === 0) return rows;
  const out: ShedExecutionRow[] = [rows[0]!];
  for (let i = 1; i < rows.length; i++) {
    const cur = rows[i]!;
    const prev = rows[i - 1]!;
    if (!shedExecutionAuditEqual(cur, prev)) {
      out.push(cur);
    }
  }
  return out;
}
