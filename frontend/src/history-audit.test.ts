import { describe, expect, it } from "vitest";

import {
  dedupeConsecutiveExecutions,
  dedupeConsecutiveShedExecutions,
  executionAuditEqual,
  shedExecutionAuditEqual,
} from "./history-audit.js";
import type { ExecutionHistoryRow, ShedExecutionRow } from "./types.js";

const exec = (overrides: Partial<ExecutionHistoryRow> = {}): ExecutionHistoryRow => ({
  ts: "2026-06-28T10:00:00Z",
  capability: "max_grid_charge_current",
  requested: "32",
  applied: false,
  verified: false,
  skipped_reason: "engine.skip.already_set",
  error: null,
  ...overrides,
});

const shed = (overrides: Partial<ShedExecutionRow> = {}): ShedExecutionRow => ({
  ts: "2026-06-28T10:00:00Z",
  tier: "pool",
  entity: "switch.pool",
  desired_on: false,
  applied: false,
  verified: false,
  skipped_reason: "engine.skip.shadow_mode",
  error: null,
  ...overrides,
});

describe("executionAuditEqual", () => {
  it("ignores ts", () => {
    expect(executionAuditEqual(exec(), exec({ ts: "2026-06-28T11:00:00Z" }))).toBe(true);
  });

  it("detects requested change", () => {
    expect(executionAuditEqual(exec(), exec({ requested: "40" }))).toBe(false);
  });
});

describe("dedupeConsecutiveExecutions", () => {
  it("keeps newest and drops older consecutive duplicates", () => {
    const rows = [
      exec({ ts: "2026-06-28T11:00:00Z" }),
      exec({ ts: "2026-06-28T10:00:00Z" }),
      exec({ ts: "2026-06-28T09:00:00Z", requested: "40" }),
    ];
    expect(dedupeConsecutiveExecutions(rows)).toHaveLength(2);
    expect(dedupeConsecutiveExecutions(rows)[0]?.ts).toBe("2026-06-28T11:00:00Z");
  });
});

describe("shedExecutionAuditEqual", () => {
  it("ignores ts", () => {
    expect(shedExecutionAuditEqual(shed(), shed({ ts: "2026-06-28T11:00:00Z" }))).toBe(true);
  });
});

describe("dedupeConsecutiveShedExecutions", () => {
  it("drops consecutive duplicate shed rows", () => {
    const rows = [
      shed({ ts: "2026-06-28T11:00:00Z" }),
      shed({ ts: "2026-06-28T10:00:00Z" }),
    ];
    expect(dedupeConsecutiveShedExecutions(rows)).toHaveLength(1);
  });
});
