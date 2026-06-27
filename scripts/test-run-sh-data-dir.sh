#!/usr/bin/env bash
# Regression: HA Supervisor apps must persist to /data, not image default /app/data.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

LIB="$ROOT/scripts/lib/addon-data-dir.sh"

# Simulate image ENV (Dockerfile sets these before run.sh).
export DATA_DIR=/app/data
export DATABASE_URL=sqlite+aiosqlite:////app/data/solar.db

# --- Test 1: /data present forces persistence paths ---
FAKE_DATA="$TMP/data"
mkdir -p "$FAKE_DATA"
export SOLAR_ADDON_DATA_ROOT="$FAKE_DATA"
# shellcheck disable=SC1090
. "$LIB"
if [ "$DATA_DIR" != "$FAKE_DATA" ]; then
  echo "FAIL: expected DATA_DIR=$FAKE_DATA, got DATA_DIR=$DATA_DIR" >&2
  exit 1
fi
if [ "$DATABASE_URL" != "sqlite+aiosqlite:///${FAKE_DATA}/solar.db" ]; then
  echo "FAIL: unexpected DATABASE_URL=$DATABASE_URL" >&2
  exit 1
fi

# --- Test 2: no /data leaves Docker defaults ---
export DATA_DIR=/app/data
export DATABASE_URL=sqlite+aiosqlite:////app/data/solar.db
unset SOLAR_ADDON_DATA_ROOT
NO_DATA="$TMP/absent"
# Point at a path that does not exist so the block is skipped.
export SOLAR_ADDON_DATA_ROOT="$NO_DATA"
# shellcheck disable=SC1090
. "$LIB"
if [ "$DATA_DIR" != /app/data ]; then
  echo "FAIL: compose path should keep DATA_DIR=/app/data when /data absent" >&2
  exit 1
fi

# --- Test 3: migration copies legacy config.runtime.yaml ---
LEGACY_APP="$TMP/app-data"
mkdir -p "$LEGACY_APP" "$FAKE_DATA"
echo "legacy: true" > "$LEGACY_APP/config.runtime.yaml"
rm -f "$FAKE_DATA/config.runtime.yaml"

export DATA_DIR=/app/data
export DATABASE_URL=sqlite+aiosqlite:////app/data/solar.db
export SOLAR_ADDON_DATA_ROOT="$FAKE_DATA"
export SOLAR_APP_DATA_ROOT="$LEGACY_APP"
# shellcheck disable=SC1090
. "$LIB"
if ! grep -q "legacy: true" "$FAKE_DATA/config.runtime.yaml"; then
  echo "FAIL: migration did not copy config.runtime.yaml" >&2
  exit 1
fi

# --- Test 4: run.sh sources shared lib ---
if ! grep -q 'addon-data-dir.sh' "$ROOT/run.sh"; then
  echo "FAIL: run.sh does not source addon-data-dir.sh" >&2
  exit 1
fi

echo "run.sh DATA_DIR tests passed"
