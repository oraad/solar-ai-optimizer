#!/usr/bin/env bash
# Dashboard self-update / restore helper. Spawned detached from the app container
# with --entrypoint /app/scripts/docker-self-update.sh (not run.sh).
set -euo pipefail

OPERATION="${1:-update}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/pull-progress.sh
source "${SCRIPT_DIR}/lib/pull-progress.sh"

CONTAINER="${CONTAINER:-solar-optimizer}"
DATA_VOL="${DATA_VOL:-solar-data}"
DATA_PATH="${DATA_PATH:-/app/data}"
PORT="${PORT:-8000}"
ENV_FILE="${ENV_FILE:-}"
TARGET_IMAGE="${TARGET_IMAGE:-}"
FROM_VERSION="${FROM_VERSION:-}"
TO_VERSION="${TO_VERSION:-}"
BACKUP_NAME="${BACKUP_NAME:-}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"
BACKUP_DIR="${BACKUP_DIR:-.update-backups}"
BACKUP_RETENTION="${BACKUP_RETENTION:-3}"
LOCK_FILE="${LOCK_FILE:-.update_in_progress}"
PENDING_FILE="${PENDING_FILE:-.update_pending.json}"
FAILED_FILE="${FAILED_FILE:-.update_failed.json}"
PROGRESS_FILE="${PROGRESS_FILE:-.update_progress.json}"
DEPLOY_STATE="${DEPLOY_STATE:-.deploy_state.json}"
ENV_SNAPSHOT="${DATA_PATH}/.update-env-snapshot"
CONTAINER_OLD="${CONTAINER}_old"
HEALTH_INTERVAL=2

LOG_DIR="${DATA_PATH}/.update-logs"
LOG_FILE="${LOG_DIR}/$(date +%s).log"
LATEST_LOG="${LOG_DIR}/latest.log"

mkdir -p "$LOG_DIR" "$DATA_PATH"
exec > >(tee -a "$LOG_FILE") 2>&1
ln -sf "$(basename "$LOG_FILE")" "$LATEST_LOG" 2>/dev/null || cp -f "$LOG_FILE" "$LATEST_LOG" 2>/dev/null || true

STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u)"
LAST_PROGRESS_WRITE=0

touch_lock_heartbeat() {
  local lock="${DATA_PATH}/${LOCK_FILE}"
  if [ -f "$lock" ]; then
    touch "$lock" 2>/dev/null || true
  fi
}

write_progress() {
  local stage="$1" message="$2"
  local pull_detail="${3:-}" pull_percent="${4:-}"
  local now throttle_ok=1
  now="$(date +%s)"
  if [ "$stage" = "pulling" ] && [ -n "$pull_percent" ]; then
    if [ $((now - LAST_PROGRESS_WRITE)) -lt 1 ] && [ "${FORCE_PROGRESS_WRITE:-0}" != "1" ]; then
      return 0
    fi
  fi
  LAST_PROGRESS_WRITE="$now"

  STAGE="$stage" MESSAGE="$message" PULL_DETAIL="$pull_detail" PULL_PERCENT="$pull_percent" \
    OPERATION="$OPERATION" FROM_VERSION="$FROM_VERSION" TO_VERSION="$TO_VERSION" \
    STARTED_AT="$STARTED_AT" DATA_PATH="$DATA_PATH" PROGRESS_FILE="$PROGRESS_FILE" \
    python3 <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
payload = {
    "operation": os.environ["OPERATION"],
    "stage": os.environ["STAGE"],
    "message": os.environ["MESSAGE"],
    "from_version": os.environ.get("FROM_VERSION") or None,
    "to_version": os.environ.get("TO_VERSION") or None,
    "started_at": os.environ.get("STARTED_AT") or now,
    "updated_at": now,
}
detail = os.environ.get("PULL_DETAIL", "")
if detail:
    payload["pull_detail"] = detail
pct = os.environ.get("PULL_PERCENT", "")
if pct != "":
    payload["pull_percent"] = int(pct)
path = Path(os.environ["DATA_PATH"]) / os.environ["PROGRESS_FILE"]
path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
PY
  touch_lock_heartbeat
}

write_failed() {
  local msg="$1" backup="${2:-}"
  STAGE="failed" MESSAGE="$msg" PULL_DETAIL="" PULL_PERCENT="" \
    OPERATION="$OPERATION" FROM_VERSION="$FROM_VERSION" TO_VERSION="$TO_VERSION" \
    STARTED_AT="$STARTED_AT" DATA_PATH="$DATA_PATH" PROGRESS_FILE="$PROGRESS_FILE" \
    python3 <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
payload = {
    "operation": os.environ["OPERATION"],
    "stage": "failed",
    "message": os.environ["MESSAGE"],
    "from_version": os.environ.get("FROM_VERSION") or None,
    "to_version": os.environ.get("TO_VERSION") or None,
    "started_at": os.environ.get("STARTED_AT") or now,
    "updated_at": now,
}
path = Path(os.environ["DATA_PATH"]) / os.environ["PROGRESS_FILE"]
path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
PY
  FAIL_MSG="$msg" FAIL_BACKUP="$backup" DATA_PATH="$DATA_PATH" FAILED_FILE="$FAILED_FILE" \
    python3 <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["DATA_PATH"]) / os.environ["FAILED_FILE"]
path.write_text(
    json.dumps({"message": os.environ["FAIL_MSG"], "backup": os.environ.get("FAIL_BACKUP") or None}),
    encoding="utf-8",
)
PY
}

cleanup_env_snapshot() {
  rm -f "$ENV_SNAPSHOT" 2>/dev/null || true
}

cleanup_pull_state() {
  rm -rf "${DATA_PATH}/.update-pull-state" 2>/dev/null || true
}

fail() {
  local msg="$1"
  local backup="${2:-}"
  echo "ERROR: $msg"
  write_failed "$msg" "$backup"
  cleanup_env_snapshot
  cleanup_pull_state
  rm -f "${DATA_PATH}/${LOCK_FILE}" "${DATA_PATH}/${PENDING_FILE}" "${DATA_PATH}/${PROGRESS_FILE}" 2>/dev/null || true
  exit 1
}

success_cleanup() {
  cleanup_env_snapshot
  cleanup_pull_state
  rm -f "${DATA_PATH}/${LOCK_FILE}" "${DATA_PATH}/${PENDING_FILE}" "${DATA_PATH}/${FAILED_FILE}" \
    "${DATA_PATH}/${PROGRESS_FILE}" 2>/dev/null || true
}

remove_stale_old() {
  if docker inspect "$CONTAINER_OLD" >/dev/null 2>&1; then
    echo "Removing stale ${CONTAINER_OLD}"
    docker rm -f "$CONTAINER_OLD" 2>/dev/null || true
  fi
}

snapshot_env_if_needed() {
  if [ -n "$ENV_FILE" ]; then
    return 0
  fi
  if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
    return 0
  fi
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$CONTAINER" >"$ENV_SNAPSHOT" 2>/dev/null || true
}

resolve_env_args() {
  ENV_ARGS=""
  if [ -n "$ENV_FILE" ]; then
    ENV_ARGS="--env-file ${ENV_FILE}"
  elif [ -f "$ENV_SNAPSHOT" ]; then
    ENV_ARGS="--env-file ${ENV_SNAPSHOT}"
  fi
}

run_solar_container() {
  local image="$1"
  # shellcheck disable=SC2086
  docker run -d --name "$CONTAINER" --restart unless-stopped \
    --health-cmd="curl -fsS http://localhost:8000/api/health || exit 1" \
    --health-interval=10s --health-timeout=5s --health-retries=3 --health-start-period=25s \
    $ENV_ARGS \
    -e SELF_UPDATE_ENABLED=true \
    -e "SELF_UPDATE_ENV_FILE=${ENV_FILE}" \
    -e "SELF_UPDATE_IMAGE=${image}" \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "${DATA_VOL}:${DATA_PATH}" \
    -p "${PORT}:8000" \
    "$image"
}

wait_healthy() {
  local attempt=0
  local max_attempts=$((HEALTH_TIMEOUT / HEALTH_INTERVAL))
  [ "$max_attempts" -lt 1 ] && max_attempts=1

  write_progress "verifying" "Health check 0/${max_attempts}"

  while [ "$attempt" -lt "$max_attempts" ]; do
    attempt=$((attempt + 1))
    write_progress "verifying" "Health check ${attempt}/${max_attempts}"

    if docker exec "$CONTAINER" curl -fsS "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
      return 0
    fi

    local hstatus
    hstatus="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$CONTAINER" 2>/dev/null || true)"
    if [ "$hstatus" = "healthy" ]; then
      return 0
    fi

    if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
      return 1
    fi
    local running
    running="$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || echo false)"
    if [ "$running" != "true" ]; then
      return 1
    fi

    sleep "$HEALTH_INTERVAL"
  done
  return 1
}

rollback_to_old() {
  echo "Rolling back to ${CONTAINER_OLD}"
  docker rm -f "$CONTAINER" 2>/dev/null || true
  if docker inspect "$CONTAINER_OLD" >/dev/null 2>&1; then
    docker rename "$CONTAINER_OLD" "$CONTAINER"
    docker update --restart=unless-stopped "$CONTAINER" >/dev/null 2>&1 || true
    docker start "$CONTAINER" 2>/dev/null || true
  fi
}

atomic_swap() {
  local target_image="$1"
  local allow_rollback="${2:-true}"
  write_progress "stopping" "Stopping current container"
  remove_stale_old

  if docker inspect "$CONTAINER" >/dev/null 2>&1; then
    docker stop "$CONTAINER" 2>/dev/null || true
    docker rename "$CONTAINER" "$CONTAINER_OLD"
    docker update --restart=no "$CONTAINER_OLD" >/dev/null 2>&1 || true
  fi

  write_progress "recreating" "Starting updated container"
  resolve_env_args
  if ! run_solar_container "$target_image"; then
    if [ "$allow_rollback" = "true" ]; then
      rollback_to_old
    else
      docker rm -f "$CONTAINER" 2>/dev/null || true
    fi
    fail "container recreate failed" "${BACKUP:-}"
  fi

  if ! wait_healthy; then
    if [ "$allow_rollback" = "true" ]; then
      rollback_to_old
      fail "new container failed health check; rolled back" "${BACKUP:-}"
    else
      docker rm -f "$CONTAINER" 2>/dev/null || true
      fail "new container failed health check after restore" "${BACKUP_NAME}"
    fi
  fi

  if docker inspect "$CONTAINER_OLD" >/dev/null 2>&1; then
    docker rm -f "$CONTAINER_OLD" 2>/dev/null || true
  fi
}

do_backup() {
  BACKUP="${BACKUP_DIR}/pre-from-${FROM_VERSION}-to-${TO_VERSION}-$(date +%s).tar.gz"
  write_progress "backing_up" "Backing up data"
  docker run --rm -v "${DATA_VOL}:/data" alpine sh -c \
    "mkdir -p /data/${BACKUP_DIR} && tar czf /data/${BACKUP} -C /data --exclude=${BACKUP_DIR} --exclude=.update-logs ." \
    || fail "backup failed"

  docker run --rm -v "${DATA_VOL}:/data" alpine sh -c \
    "cd /data/${BACKUP_DIR} && ls -1t pre-*.tar.gz 2>/dev/null | tail -n +$((BACKUP_RETENTION + 1)) | while read -r f; do rm -f \"\$f\"; done" \
    2>/dev/null || true
}

do_pull() {
  write_progress "pulling" "Pulling ${TARGET_IMAGE}"
  PULL_STATE_DIR="${DATA_PATH}/.update-pull-state"
  pull_progress_reset

  local line pct last_detail=""
  while IFS= read -r line; do
    echo "$line"
    pull_process_line "$line"
    last_detail="$line"
    pct="$(pull_percent_compute || true)"
    if [ -n "$pct" ]; then
      write_progress "pulling" "Pulling ${TARGET_IMAGE}" "$last_detail" "$pct"
    else
      write_progress "pulling" "Pulling ${TARGET_IMAGE}" "$last_detail"
    fi
  done < <(docker pull --progress=plain "$TARGET_IMAGE" 2>&1) || fail "docker pull failed" "${BACKUP:-}"

  FORCE_PROGRESS_WRITE=1
  write_progress "pulling" "Pulling ${TARGET_IMAGE}" "${last_detail}" "100"
  unset FORCE_PROGRESS_WRITE
  cleanup_pull_state
}

write_deploy_state() {
  local version="$1" image="$2" prev_version="$3" prev_image="$4" last_backup="$5" restored="$6"
  DEPLOY_VERSION="$version" DEPLOY_IMAGE="$image" DEPLOY_PREV_VERSION="$prev_version" \
    DEPLOY_PREV_IMAGE="$prev_image" DEPLOY_LAST_BACKUP="$last_backup" DEPLOY_RESTORED="$restored" \
    DEPLOY_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)" DATA_PATH="$DATA_PATH" DEPLOY_STATE="$DEPLOY_STATE" \
    python3 <<'PY'
import json
import os
from pathlib import Path

payload = {
    "version": os.environ["DEPLOY_VERSION"],
    "image": os.environ["DEPLOY_IMAGE"],
    "previous_version": os.environ.get("DEPLOY_PREV_VERSION") or None,
    "previous_image": os.environ.get("DEPLOY_PREV_IMAGE") or None,
    "deployed_at": os.environ["DEPLOY_AT"],
    "last_backup": os.environ.get("DEPLOY_LAST_BACKUP") or None,
    "restored_from_backup": os.environ.get("DEPLOY_RESTORED") == "true",
}
path = Path(os.environ["DATA_PATH"]) / os.environ["DEPLOY_STATE"]
path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
PY
}

cmd_update() {
  [ -z "$TARGET_IMAGE" ] && fail "TARGET_IMAGE not set"
  write_progress "starting" "Preparing update"
  remove_stale_old

  PREVIOUS_IMAGE=""
  if docker inspect "$CONTAINER" >/dev/null 2>&1; then
    PREVIOUS_IMAGE="$(docker inspect -f '{{.Config.Image}}' "$CONTAINER" 2>/dev/null || echo "")"
  fi

  snapshot_env_if_needed
  do_backup
  do_pull

  docker volume inspect "$DATA_VOL" >/dev/null 2>&1 || docker volume create "$DATA_VOL" >/dev/null
  atomic_swap "$TARGET_IMAGE"

  write_progress "finishing" "Finalizing"
  write_deploy_state "$TO_VERSION" "$TARGET_IMAGE" "$FROM_VERSION" "$PREVIOUS_IMAGE" "$BACKUP" "false"
  success_cleanup
  echo "Update complete: ${TARGET_IMAGE}"
}

cmd_restore() {
  [ -z "$TARGET_IMAGE" ] && fail "TARGET_IMAGE not set"
  [ -z "$BACKUP_NAME" ] && fail "BACKUP_NAME not set"

  write_progress "starting" "Preparing restore"
  remove_stale_old

  if ! docker run --rm -v "${DATA_VOL}:/data" alpine sh -c "test -f /data/${BACKUP_DIR}/${BACKUP_NAME}"; then
    fail "backup not found" "$BACKUP_NAME"
  fi

  PREVIOUS_IMAGE=""
  if docker inspect "$CONTAINER" >/dev/null 2>&1; then
    PREVIOUS_IMAGE="$(docker inspect -f '{{.Config.Image}}' "$CONTAINER" 2>/dev/null || echo "")"
  fi

  snapshot_env_if_needed

  write_progress "stopping" "Stopping current container"
  if docker inspect "$CONTAINER" >/dev/null 2>&1; then
    docker stop "$CONTAINER" 2>/dev/null || true
    docker rename "$CONTAINER" "$CONTAINER_OLD"
    docker update --restart=no "$CONTAINER_OLD" >/dev/null 2>&1 || true
  fi

  write_progress "restoring_data" "Restoring backup data"
  docker run --rm -v "${DATA_VOL}:/data" alpine sh -c \
    "cd /data && find . -mindepth 1 -maxdepth 1 ! -name ${BACKUP_DIR} ! -name .update-logs -exec rm -rf {} +" \
    || fail "clear data failed" "$BACKUP_NAME"

  docker run --rm -v "${DATA_VOL}:/data" alpine sh -c \
    "tar xzf /data/${BACKUP_DIR}/${BACKUP_NAME} -C /data" \
    || fail "extract backup failed" "$BACKUP_NAME"

  # Remove old container before swap creates new one
  docker rm -f "$CONTAINER_OLD" 2>/dev/null || true

  atomic_swap "$TARGET_IMAGE" false

  write_progress "finishing" "Finalizing"
  write_deploy_state "$TO_VERSION" "$TARGET_IMAGE" "" "" "${BACKUP_DIR}/${BACKUP_NAME}" "true"
  success_cleanup
  echo "Restore complete: ${TARGET_IMAGE}"
}

case "$OPERATION" in
  update) cmd_update ;;
  restore) cmd_restore ;;
  *)
    echo "Usage: $0 update|restore" >&2
    exit 1
    ;;
esac
