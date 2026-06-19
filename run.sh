#!/bin/sh
# Universal entrypoint. Runs identically under docker-compose and as a Home
# Assistant add-on. When launched as an add-on, /data exists and the user's
# options live in /data/options.json; we translate those into the env vars the
# app expects, then start the server.
set -e

OPTIONS=/data/options.json

# Add-ons get a writable /data; use it for persistence + the supervisor DB path.
if [ -d /data ]; then
  export DATA_DIR="${DATA_DIR:-/data}"
  export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:////data/solar.db}"
fi

if [ -f "$OPTIONS" ]; then
  echo "Home Assistant add-on options detected; applying."
  eval "$(python - <<'PY'
import json, shlex
try:
    opts = json.load(open('/data/options.json'))
except Exception:
    opts = {}
# Map add-on option keys -> app env vars.
mapping = {
    'shadow_mode': 'SHADOW_MODE',
    'log_level': 'LOG_LEVEL',
    'log_format': 'LOG_FORMAT',
    'ha_base_url': 'HA_BASE_URL',
    'ha_token': 'HA_TOKEN',
    'ha_verify_ssl': 'HA_VERIFY_SSL',
    'ml_load_enabled': 'ML_LOAD_ENABLED',
    'llm_enabled': 'LLM_ENABLED',
    'ollama_base_url': 'OLLAMA_BASE_URL',
    'ollama_model': 'OLLAMA_MODEL',
    'solcast_api_key': 'SOLCAST_API_KEY',
    'solcast_resource_id': 'SOLCAST_RESOURCE_ID',
    'api_token': 'API_TOKEN',
}
for key, val in opts.items():
    env = mapping.get(key, key.upper())
    if isinstance(val, bool):
        val = 'true' if val else 'false'
    print(f'export {env}={shlex.quote(str(val))}')
PY
)"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
