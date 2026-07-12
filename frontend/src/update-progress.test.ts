import { describe, expect, it } from "vitest";

import {
  activeStageIndex,
  flowStages,
  pullProgressLabel,
  stageLabel,
  UPDATE_FLOW_STAGES,
} from "./update-progress.js";
import type { UpdateProgress } from "./types.js";

describe("update-progress", () => {
  it("includes verifying after recreating in update flow", () => {
    const stages = flowStages("update");
    const recreating = stages.indexOf("recreating");
    const verifying = stages.indexOf("verifying");
    expect(recreating).toBeGreaterThanOrEqual(0);
    expect(verifying).toBe(recreating + 1);
    expect(UPDATE_FLOW_STAGES).toContain("verifying");
  });

  it("stageLabel prefers progress.message for active stage", () => {
    const progress: UpdateProgress = {
      operation: "update",
      stage: "verifying",
      message: "Health check 3/60",
    };
    expect(stageLabel("verifying", progress)).toBe("Health check 3/60");
  });

  it("activeStageIndex treats healthWait as post-flow restart state", () => {
    const stages = flowStages("update");
    const progress: UpdateProgress = {
      operation: "update",
      stage: "recreating",
      message: "Starting updated container",
    };
    expect(activeStageIndex(stages, progress, true, false)).toBe(stages.length);
  });

  it("activeStageIndex uses starting when in progress with no progress payload", () => {
    const stages = flowStages("update");
    expect(activeStageIndex(stages, null, false, true)).toBe(0);
    expect(stages[0]).toBe("starting");
  });

  it("activeStageIndex marks flow complete when idle with no progress", () => {
    const stages = flowStages("update");
    expect(activeStageIndex(stages, null, false, false)).toBe(stages.length);
  });

  it("pullProgressLabel includes percent when set", () => {
    const progress: UpdateProgress = {
      operation: "update",
      stage: "pulling",
      message: "Pulling image",
      pull_percent: 42,
    };
    expect(pullProgressLabel(progress)).toContain("42%");
  });

  it("pullProgressLabel omits percent when null", () => {
    const progress: UpdateProgress = {
      operation: "update",
      stage: "pulling",
      message: "Pulling image",
    };
    expect(pullProgressLabel(progress)).not.toContain("%");
  });
});
