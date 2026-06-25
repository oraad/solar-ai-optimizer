import type { UpdateProgress, UpdateStage } from "./types.js";
import { t } from "./i18n.js";

export const UPDATE_FLOW_STAGES: UpdateStage[] = [
  "starting",
  "backing_up",
  "pulling",
  "stopping",
  "recreating",
  "verifying",
  "finishing",
];

export const RESTORE_FLOW_STAGES: UpdateStage[] = [
  "starting",
  "stopping",
  "restoring_data",
  "recreating",
  "verifying",
  "finishing",
];

export function flowStages(operation: UpdateProgress["operation"]): UpdateStage[] {
  return operation === "restore" ? RESTORE_FLOW_STAGES : UPDATE_FLOW_STAGES;
}

export function stageIndex(stages: UpdateStage[], stage: UpdateStage): number {
  const idx = stages.indexOf(stage);
  return idx >= 0 ? idx : 0;
}

export function stageLabel(stage: UpdateStage, progress?: UpdateProgress | null): string {
  if (stage === "pulling" && progress?.stage === "pulling") {
    return pullProgressLabel(progress);
  }
  if (progress?.message && progress.stage === stage) {
    return progress.message;
  }
  const key = `update.stages.${stage}`;
  const label = t(key);
  return label === key ? stage : label;
}

export function pullProgressLabel(progress: UpdateProgress): string {
  const base = t("update.stages.pulling");
  if (progress.pull_percent != null && progress.pull_percent >= 0) {
    return `${base.replace("…", "")}… ${progress.pull_percent}%`;
  }
  return base;
}

export function activeStageIndex(
  stages: UpdateStage[],
  progress: UpdateProgress | null | undefined,
  healthWait: boolean,
  updateInProgress: boolean,
): number {
  if (healthWait) {
    return stages.length;
  }
  const activeStage = progress?.stage ?? (updateInProgress ? "starting" : null);
  if (!activeStage) {
    return stages.length;
  }
  if (activeStage === "failed") {
    return stageIndex(stages, "finishing");
  }
  return stageIndex(stages, activeStage);
}

export function updateChipLabel(progress: UpdateProgress | null | undefined): string {
  if (!progress) {
    return t("update.chipUpdating");
  }
  if (progress.stage === "pulling") {
    const label = pullProgressLabel(progress);
    return t("update.chipPrefix", { label: label.replace("…", "").trim() });
  }
  const msg = stageLabel(progress.stage, progress);
  return t("update.chipPrefix", { label: msg.replace("…", "").trim() });
}

export function progressHeaderTitle(
  progress: UpdateProgress | null | undefined,
  healthWait: boolean,
): string {
  if (healthWait) {
    return t("update.restarting");
  }
  if (progress?.from_version && progress?.to_version) {
    return t("update.updatingVersion", {
      from: progress.from_version,
      to: progress.to_version,
    });
  }
  return progress?.operation === "restore"
    ? t("update.restoreInProgress")
    : t("update.updateInProgress");
}

export function updateLogHint(): string {
  return t("update.logHint");
}
