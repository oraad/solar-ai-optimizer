#!/usr/bin/env bash
# Shared constants and helpers for Solar AI Optimizer Proxmox scripts.

SOLAR_IMAGE="${SOLAR_IMAGE:-ghcr.io/oraad/solar-ai-optimizer}"
SOLAR_IMAGE_TAG="${SOLAR_IMAGE_TAG:-latest}"
SOLAR_CONTAINER="${SOLAR_CONTAINER:-solar-optimizer}"
SOLAR_DATA_VOLUME="${SOLAR_DATA_VOLUME:-solar-data}"
SOLAR_DATA_PATH="${SOLAR_DATA_PATH:-/app/data}"
SOLAR_PORT="${SOLAR_PORT:-8000}"
SOLAR_HEALTH_PATH="${SOLAR_HEALTH_PATH:-/api/health}"
SOLAR_INSTALL_DIR="${SOLAR_INSTALL_DIR:-/opt/solar-ai-optimizer}"
SOLAR_VERSION_FILE="${SOLAR_VERSION_FILE:-/opt/solar-ai-optimizer_version.txt}"
SOLAR_ENV_FILE="${SOLAR_INSTALL_DIR}/solar.env"
SOLAR_REPO_RAW="${SOLAR_REPO_RAW:-https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main}"

solar_image_ref() {
  echo "${SOLAR_IMAGE}:${SOLAR_IMAGE_TAG}"
}

solar_default_env() {
  cat <<'EOF'
SHADOW_MODE=true
LOG_LEVEL=INFO
DATA_DIR=/app/data
DATABASE_URL=sqlite+aiosqlite:////app/data/solar.db
EOF
}

solar_write_env_file() {
  mkdir -p "$SOLAR_INSTALL_DIR"
  solar_default_env >"$SOLAR_ENV_FILE"
  cat >>"$SOLAR_ENV_FILE" <<'EOF'

# Optional overrides (uncomment and set as needed):
# API_TOKEN=change-me
# HA_BASE_URL=http://homeassistant.local:8123
# HA_TOKEN=
# SOLCAST_API_KEY=
# SOLCAST_RESOURCE_ID=
# ML_LOAD_ENABLED=false
# LLM_ENABLED=false
EOF
}

solar_source_common() {
  # shellcheck disable=SC1090
  source <(curl -fsSL "${SOLAR_REPO_RAW}/proxmox/lib/solar-common.sh")
}

solar_latest_github_tag() {
  curl -fsSL "https://api.github.com/repos/oraad/solar-ai-optimizer/releases/latest" 2>/dev/null \
    | grep -Po '"tag_name":\s*"\K[^"]+' || echo "latest"
}

solar_installed_ref() {
  if [[ -f "$SOLAR_VERSION_FILE" ]]; then
    cat "$SOLAR_VERSION_FILE"
  fi
}

solar_current_image_ref() {
  docker image inspect --format='{{index .RepoDigests 0}}' "$(solar_image_ref)" 2>/dev/null \
    || docker image inspect --format='{{.Id}}' "$(solar_image_ref)" 2>/dev/null \
    || echo ""
}

solar_wait_healthy() {
  local host="${1:-127.0.0.1}"
  local port="${2:-$SOLAR_PORT}"
  local path="${3:-$SOLAR_HEALTH_PATH}"
  local timeout="${4:-120}"
  local elapsed=0

  while [[ "$elapsed" -lt "$timeout" ]]; do
    if curl -fsS "http://${host}:${port}${path}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  return 1
}

solar_ensure_data_volume() {
  docker volume inspect "$SOLAR_DATA_VOLUME" >/dev/null 2>&1 \
    || docker volume create "$SOLAR_DATA_VOLUME" >/dev/null
}

solar_run_container() {
  solar_ensure_data_volume
  docker run -d \
    --name "$SOLAR_CONTAINER" \
    --restart unless-stopped \
    --env-file "$SOLAR_ENV_FILE" \
    -v "${SOLAR_DATA_VOLUME}:${SOLAR_DATA_PATH}" \
    -p "${SOLAR_PORT}:8000" \
    "$(solar_image_ref)"
}

solar_recreate_container() {
  docker stop "$SOLAR_CONTAINER" 2>/dev/null || true
  docker rm "$SOLAR_CONTAINER" 2>/dev/null || true
  solar_run_container
}

solar_save_version() {
  local ref
  ref="$(solar_current_image_ref)"
  [[ -z "$ref" ]] && ref="$(solar_image_ref)"
  echo "$ref" >"$SOLAR_VERSION_FILE"
}

solar_is_installed() {
  [[ -d "$SOLAR_INSTALL_DIR" ]] && docker ps -a --format '{{.Names}}' | grep -qx "$SOLAR_CONTAINER"
}
