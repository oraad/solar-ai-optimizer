#!/usr/bin/env bash
# Reset local admin password for Solar AI Optimizer.
#
# Writes credentials to $DATA_DIR/local_auth.env inside the container and
# restarts the service by default so the new password takes effect.
#
# Usage:
#   ./scripts/reset-local-password.sh
#   ./scripts/reset-local-password.sh --password 'my-new-pass'
#   ./scripts/reset-local-password.sh --username admin --keep-sessions --no-restart
#
# Environment:
#   SOLAR_CONTAINER   Container name (default: solar-optimizer)
#   COMPOSE_SERVICE   Compose service name (default: solar)

set -euo pipefail

SOLAR_CONTAINER="${SOLAR_CONTAINER:-solar-optimizer}"
COMPOSE_SERVICE="${COMPOSE_SERVICE:-solar}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: reset-local-password.sh [OPTIONS]

Options:
  --password PASS     Set password (auto-generated if omitted)
  --username USER     Local admin username (default: admin)
  --keep-sessions     Do not rotate SESSION_SECRET
  --container NAME    Docker container name override
  --compose-service S Docker Compose service name (default: solar)
  --no-restart        Skip container restart after reset
  -h, --help          Show this help

Detects docker compose (from repo root) or a running container named
SOLAR_CONTAINER (default: solar-optimizer).
EOF
}

PY_ARGS=()
NO_RESTART=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h | --help)
      usage
      exit 0
      ;;
    --no-restart)
      NO_RESTART=1
      shift
      ;;
    --container)
      SOLAR_CONTAINER="${2:?--container requires a value}"
      shift 2
      ;;
    --compose-service)
      COMPOSE_SERVICE="${2:?--compose-service requires a value}"
      shift 2
      ;;
    --password | --username | --keep-sessions)
      PY_ARGS+=("$1")
      if [[ "$1" == "--keep-sessions" ]]; then
        shift
      else
        PY_ARGS+=("${2:?${1} requires a value}")
        shift 2
      fi
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

run_helper_compose() {
  (cd "$REPO_ROOT" && docker compose exec -T "$COMPOSE_SERVICE" python -m scripts.reset_local_password "${PY_ARGS[@]}")
}

run_helper_docker() {
  docker exec -T "$SOLAR_CONTAINER" python -m scripts.reset_local_password "${PY_ARGS[@]}"
}

detect_and_run() {
  if [[ -f "${REPO_ROOT}/docker-compose.yml" ]] \
    && docker compose -f "${REPO_ROOT}/docker-compose.yml" ps --status running "$COMPOSE_SERVICE" 2>/dev/null \
      | grep -q "$COMPOSE_SERVICE"; then
    run_helper_compose
    return 0
  fi
  if docker ps --format '{{.Names}}' | grep -qx "$SOLAR_CONTAINER"; then
    run_helper_docker
    return 0
  fi
  echo "Error: no running Solar container found." >&2
  echo "  Start the stack (docker compose up -d) or set --container / SOLAR_CONTAINER." >&2
  exit 1
}

restart_service() {
  if [[ "$NO_RESTART" -eq 1 ]]; then
    echo "Skipped restart (--no-restart). Restart manually for the new password to take effect."
    return 0
  fi
  if [[ -f "${REPO_ROOT}/docker-compose.yml" ]] \
    && docker compose -f "${REPO_ROOT}/docker-compose.yml" ps --status running "$COMPOSE_SERVICE" 2>/dev/null \
      | grep -q "$COMPOSE_SERVICE"; then
    (cd "$REPO_ROOT" && docker compose restart "$COMPOSE_SERVICE")
    echo "Container restarted."
    return 0
  fi
  docker restart "$SOLAR_CONTAINER"
  echo "Container restarted."
}

OUTPUT="$(detect_and_run)"
USERNAME=""
PASSWORD=""
ENV_FILE=""

while IFS= read -r line; do
  case "$line" in
    USERNAME=*) USERNAME="${line#USERNAME=}" ;;
    PASSWORD=*) PASSWORD="${line#PASSWORD=}" ;;
    ENV_FILE=*) ENV_FILE="${line#ENV_FILE=}" ;;
  esac
done <<<"$OUTPUT"

if [[ -z "$USERNAME" || -z "$PASSWORD" ]]; then
  echo "Error: password reset helper failed." >&2
  echo "$OUTPUT" >&2
  exit 1
fi

restart_service

echo ""
echo "Local admin credentials (save these — not shown again):"
echo "  Username: ${USERNAME}"
echo "  Password: ${PASSWORD}"
if [[ -n "$ENV_FILE" ]]; then
  echo "  Stored in: ${ENV_FILE}"
fi
