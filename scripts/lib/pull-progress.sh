# Layer-count pull progress parser for docker pull --progress=plain output.
# Source from docker-self-update.sh; testable via pull_progress_from_lines().

pull_progress_reset() {
  PULL_STATE_DIR="${PULL_STATE_DIR:-/tmp/solar-pull-state}"
  mkdir -p "$PULL_STATE_DIR"
  : >"$PULL_STATE_DIR/all_layers"
  : >"$PULL_STATE_DIR/done_layers"
}

pull_layer_id_from_line() {
  # Lines look like: "abc123def456: Pulling fs layer" or "abc123: Already exists"
  printf '%s' "$1" | sed -n 's/^\([a-f0-9][a-f0-9]*\):.*/\1/p' | head -1
}

pull_record_layer() {
  local id="$1"
  [ -z "$id" ] && return 0
  if ! grep -qxF "$id" "$PULL_STATE_DIR/all_layers" 2>/dev/null; then
    printf '%s\n' "$id" >>"$PULL_STATE_DIR/all_layers"
  fi
}

pull_mark_done() {
  local id="$1"
  [ -z "$id" ] && return 0
  pull_record_layer "$id"
  if ! grep -qxF "$id" "$PULL_STATE_DIR/done_layers" 2>/dev/null; then
    printf '%s\n' "$id" >>"$PULL_STATE_DIR/done_layers"
  fi
}

pull_process_line() {
  local line="$1"
  local id
  id="$(pull_layer_id_from_line "$line")"
  [ -z "$id" ] && return 0

  case "$line" in
    *"Already exists"*|*"Download complete"*|*"Pull complete"*)
      pull_mark_done "$id"
      ;;
    *"Pulling fs layer"*|*"Waiting"*|*"Verifying Checksum"*|*"Downloading"*)
      pull_record_layer "$id"
      ;;
  esac
}

pull_percent_compute() {
  local total done pct
  total="$(wc -l <"$PULL_STATE_DIR/all_layers" 2>/dev/null | tr -d ' ')"
  done="$(wc -l <"$PULL_STATE_DIR/done_layers" 2>/dev/null | tr -d ' ')"
  total="${total:-0}"
  done="${done:-0}"
  if [ "$total" -eq 0 ]; then
    return 0
  fi
  pct=$((done * 100 / total))
  if [ "$pct" -gt 99 ]; then
    pct=99
  fi
  printf '%s' "$pct"
}

# Feed lines (e.g. from tests) and print final percent.
pull_progress_from_lines() {
  pull_progress_reset
  local line
  while IFS= read -r line || [ -n "$line" ]; do
    pull_process_line "$line"
  done
  pull_percent_compute
}
