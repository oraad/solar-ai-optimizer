#!/usr/bin/env bash

# Copyright (c) 2026 oraad
# License: MIT | https://github.com/oraad/solar-ai-optimizer/blob/main/LICENSE
# Source: https://github.com/oraad/solar-ai-optimizer

SOLAR_REPO_RAW="${SOLAR_REPO_RAW:-https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main}"
SOLAR_VENDOR_RAW="${SOLAR_REPO_RAW}/proxmox/vendor/community-scripts"

# Redirect community-scripts fetches to vendored copies and our install script.
_solar_real_curl="$(command -v curl)"
curl() {
  if [[ "$1" == "-fsSL" && -n "${2:-}" ]]; then
    case "$2" in
      *community-scripts/ProxmoxVE/main/install/*-install.sh)
        "$_solar_real_curl" -fsSL "${SOLAR_REPO_RAW}/proxmox/install/solar-ai-optimizer-install.sh"
        return
        ;;
      *community-scripts/ProxmoxVE/main/*)
        local vendor_url="${2/https:\/\/raw.githubusercontent.com\/community-scripts\/ProxmoxVE\/main/${SOLAR_VENDOR_RAW}}"
        "$_solar_real_curl" -fsSL "$vendor_url"
        return
        ;;
    esac
  fi
  "$_solar_real_curl" "$@"
}

source <(curl -fsSL "${SOLAR_REPO_RAW}/proxmox/vendor/community-scripts/misc/build.func")

APP="Solar AI Optimizer"
var_tags="${var_tags:-homeassistant;solar;docker}"
var_cpu="${var_cpu:-2}"
var_ram="${var_ram:-2048}"
var_disk="${var_disk:-4}"
var_os="${var_os:-alpine}"
var_version="${var_version:-3.23}"
var_arm64="${var_arm64:-yes}"
var_unprivileged="${var_unprivileged:-1}"
var_nesting="${var_nesting:-1}"
var_keyctl="${var_keyctl:-1}"

header_info "$APP"
variables
var_install="solar-ai-optimizer-install"
color
catch_errors

function update_script() {
  header_info
  check_container_storage
  check_container_resources

  _SOLAR_REPO_RAW="${SOLAR_REPO_RAW:-https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main}"
  # shellcheck disable=SC1090
  source <(curl -fsSL "${_SOLAR_REPO_RAW}/proxmox/lib/solar-common.sh")

  if ! solar_is_installed; then
    msg_error "No ${APP} Installation Found!"
    exit
  fi

  solar_write_update_command

  local previous current env_patched=0
  previous="$(solar_installed_ref)"

  msg_info "Ensuring auth configuration"
  solar_ensure_env_auth
  env_patched="${SOLAR_ENV_PATCHED:-0}"

  msg_info "Pulling latest image"
  $STD docker pull "$(solar_image_ref)"
  msg_ok "Pulled $(solar_image_ref)"

  current="$(solar_current_image_ref)"
  if [[ -n "$previous" && "$previous" == "$current" && "$env_patched" != "1" ]]; then
    msg_ok "No update required. ${APP} is already running the latest image."
    exit
  fi

  if [[ -n "$previous" && "$previous" == "$current" ]]; then
    msg_ok "${APP} is already running the latest image."
  fi

  msg_info "Recreating container (data volume preserved)"
  $STD solar_recreate_container
  solar_save_version
  msg_ok "Container recreated"

  msg_info "Waiting for health check"
  if solar_wait_healthy 127.0.0.1 "$SOLAR_PORT" "$SOLAR_HEALTH_PATH" 120; then
    msg_ok "Service is healthy"
  else
    msg_warn "Health check timed out — check: docker logs ${SOLAR_CONTAINER}"
  fi

  solar_show_admin_credentials

  msg_ok "Updated successfully!"
  exit
}

start
build_container
description

msg_ok "Completed successfully!\n"
echo -e "${CREATING}${GN}${APP} setup has been successfully initialized!${CL}"
echo -e "${INFO}${YW}Access the dashboard at:${CL}"
echo -e "${GATEWAY}${BGN}http://${IP}:${SOLAR_PORT:-8000}${CL}"
echo -e "${INFO}${YW}Starts in SHADOW MODE — configure Home Assistant in Settings before going live.${CL}"

_SOLAR_CREDS_FILE="/opt/solar-ai-optimizer/.install-admin-credentials"
if pct exec "$CTID" test -f "$_SOLAR_CREDS_FILE" 2>/dev/null; then
  _solar_admin_user="$(pct exec "$CTID" sed -n '1p' "$_SOLAR_CREDS_FILE" 2>/dev/null | tr -d '\r')"
  _solar_admin_pass="$(pct exec "$CTID" sed -n '2p' "$_SOLAR_CREDS_FILE" 2>/dev/null | tr -d '\r')"
  pct exec "$CTID" rm -f "$_SOLAR_CREDS_FILE" 2>/dev/null || true
  if [[ -n "$_solar_admin_user" && -n "$_solar_admin_pass" ]]; then
    echo -e "${INFO}${YW}Local admin login (save these — not shown again):${CL}"
    echo -e "${INFO}${YW}Username:${CL} ${_solar_admin_user}"
    echo -e "${INFO}${YW}Password:${CL} ${_solar_admin_pass}"
  fi
fi
