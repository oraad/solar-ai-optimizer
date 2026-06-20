#!/usr/bin/env bash

# Copyright (c) 2026 oraad
# License: MIT | https://github.com/oraad/solar-ai-optimizer/blob/main/LICENSE
# Source: https://github.com/oraad/solar-ai-optimizer

source /dev/stdin <<<"$FUNCTIONS_FILE_PATH"
color
verb_ip6
catch_errors
setting_up_container
network_check
update_os

_SOLAR_REPO_RAW="${SOLAR_REPO_RAW:-https://raw.githubusercontent.com/oraad/solar-ai-optimizer/main}"
# shellcheck disable=SC1090
source <(curl -fsSL "${_SOLAR_REPO_RAW}/proxmox/lib/solar-common.sh")

msg_info "Installing Docker Engine"
DOCKER_CONFIG_PATH='/etc/docker/daemon.json'
mkdir -p "$(dirname "$DOCKER_CONFIG_PATH")"
echo -e '{\n  "log-driver": "journald"\n}' >"$DOCKER_CONFIG_PATH"
$STD sh <(curl -fsSL https://get.docker.com)
msg_ok "Installed Docker Engine"

msg_info "Pulling ${APP:-Solar AI Optimizer} image"
$STD docker pull "$(solar_image_ref)"
msg_ok "Pulled image $(solar_image_ref)"

msg_info "Configuring ${APP:-Solar AI Optimizer}"
solar_write_env_file
msg_info "Starting ${APP:-Solar AI Optimizer}"
solar_ensure_data_volume
$STD solar_run_container
solar_save_version
msg_ok "Started ${APP:-Solar AI Optimizer}"

msg_info "Waiting for health check"
if solar_wait_healthy 127.0.0.1 "$SOLAR_PORT" "$SOLAR_HEALTH_PATH" 120; then
  msg_ok "Service is healthy"
else
  msg_warn "Health check timed out — the container may still be starting"
  msg_warn "Check logs: docker logs ${SOLAR_CONTAINER}"
fi

solar_show_admin_credentials

motd_ssh
customize
solar_write_update_command
cleanup_lxc
