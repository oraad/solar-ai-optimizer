#!/bin/sh
# Universal entrypoint. Runs identically under docker-compose and as a Home
# Assistant add-on. When launched as an add-on, /data exists and the user's
# options live in /data/options.json; we translate those into the env vars the
# app expects, then start the server.
set -e

OPTIONS=/data/options.json

# Add-ons get a writable /data; use it for persistence + the supervisor DB path.
# Force /data (not image default /app/data) when the Supervisor mount exists.
# shellcheck disable=SC1091
. "$(dirname "$0")/scripts/lib/addon-data-dir.sh"

if [ -f "$OPTIONS" ]; then
  echo "Home Assistant add-on options detected; applying."
  eval "$(python - <<'PY'
import json, shlex
try:
    opts = json.load(open('/data/options.json'))
except Exception:
    opts = {}
# Map add-on option keys -> app env vars.
# Legacy ha_token / ha_base_url are no longer in the options schema and are
# not mapped (add-on uses SUPERVISOR_TOKEN). api_token remains mapped for
# upgrades that still have it in options.json (Solar inbound API auth).
mapping = {
    'prerelease_updates': 'ADDON_PRERELEASE_UPDATES',
    'shadow_mode': 'SHADOW_MODE',
    'log_level': 'LOG_LEVEL',
    'log_format': 'LOG_FORMAT',
    'ha_verify_ssl': 'HA_VERIFY_SSL',
    'ml_load_enabled': 'ML_LOAD_ENABLED',
    'llm_enabled': 'LLM_ENABLED',
    'ollama_base_url': 'OLLAMA_BASE_URL',
    'ollama_model': 'OLLAMA_MODEL',
    'solcast_api_key': 'SOLCAST_API_KEY',
    'solcast_resource_id': 'SOLCAST_RESOURCE_ID',
    'api_token': 'API_TOKEN',
    'mcp_enabled': 'MCP_ENABLED',
    'mcp_token': 'MCP_TOKEN',
}
for key, val in opts.items():
    env = mapping.get(key, key.upper())
    if isinstance(val, bool):
        val = 'true' if val else 'false'
    print(f'export {env}={shlex.quote(str(val))}')
PY
)"
fi

# Local admin credentials written by scripts/reset-local-password.sh override
# container env for auth keys (survives container recreate on the data volume).
LOCAL_AUTH_ENV="${DATA_DIR}/local_auth.env"
if [ -f "$LOCAL_AUTH_ENV" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$LOCAL_AUTH_ENV"
  set +a
fi

# Standalone MCP settings from the data volume (Settings → Agent access).
# Skip when running as an HA add-on — options.json remains the source of truth.
MCP_ENV="${DATA_DIR}/mcp.env"
if [ ! -f "$OPTIONS" ] && [ -f "$MCP_ENV" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$MCP_ENV"
  set +a
fi

# WebSocket keepalive: align with the 30s app heartbeat in api/ws.py; tolerate LAN latency.
WS_PING_INTERVAL="${WS_PING_INTERVAL:-30}"
WS_PING_TIMEOUT="${WS_PING_TIMEOUT:-60}"

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  --ws-ping-interval "$WS_PING_INTERVAL" \
  --ws-ping-timeout "$WS_PING_TIMEOUT"
