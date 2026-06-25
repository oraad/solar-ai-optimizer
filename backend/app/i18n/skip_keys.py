"""Stable skip-reason key helpers."""

from __future__ import annotations

import json

SKIP_CAPABILITY_NOT_MAPPED = "engine.skip.capability_not_mapped"
SKIP_HARD_BOUND_REJECT = "engine.skip.hard_bound_reject"
SKIP_HA_STALE = "engine.skip.ha_stale"
SKIP_SHADOW_MODE = "engine.skip.shadow_mode"
SKIP_NO_SHED_SNAPSHOT = "engine.skip.no_shed_snapshot"
SKIP_WAS_OFF_BEFORE_SHED = "engine.skip.was_off_before_shed"
SKIP_RECENTLY_WRITTEN = "engine.skip.recently_written"
SKIP_ALREADY_SET = "engine.skip.already_set"
SKIP_RATE_LIMITED = "engine.skip.rate_limited"

REJECT_NEGATIVE_GRID_CHARGE = "engine.reject.negative_grid_charge"
REJECT_EXCEEDS_MAX_GRID_CHARGE = "engine.reject.exceeds_max_grid_charge"


def skip_key(key: str, /, **params: str | int | float) -> str:
    if not params:
        return key
    return json.dumps({"k": key, "p": params}, ensure_ascii=False, separators=(",", ":"))
