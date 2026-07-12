"""Serialize Msg values and localize API payloads."""

from __future__ import annotations

import json
from typing import Any

from zoneinfo import ZoneInfo

from ..models import Msg
from ..tz import format_site_local_iso, is_utc_serializable, parse_api_utc
from . import get_locale, normalize_skip_key, skip_reason_label, t

_SKIP_FIELDS = frozenset({"skipped_reason"})

_DATETIME_KEYS = frozenset({
    "ts",
    "last_updated",
    "generated_at",
    "last_seen",
    "time",
    "heartbeat_last_pulse",
    "forecast_generated_at",
    "captured_at",
    "created_at",
    "checked_at",
    "release_checked_at",
    "published_at",
    "started_at",
    "updated_at",
})


def encode_msg(value: Msg) -> str:
    return json.dumps(
        {"k": value.key, "p": value.params},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def decode_msg(raw: str | Msg | dict[str, Any] | None) -> Msg | str | None:
    if raw is None:
        return None
    if isinstance(raw, Msg):
        return raw
    if isinstance(raw, dict):
        if "key" in raw:
            return Msg(key=str(raw["key"]), params=dict(raw.get("params") or {}))
        if "k" in raw:
            return Msg(key=str(raw["k"]), params=dict(raw.get("p") or {}))
    text = raw.strip()
    if not text:
        return ""
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return raw
        if isinstance(data, dict) and "k" in data:
            return Msg(key=str(data["k"]), params=dict(data.get("p") or {}))
        if isinstance(data, dict) and "key" in data:
            return Msg(key=str(data["key"]), params=dict(data.get("params") or {}))
    return raw


def _expand_ramp_note(note_msg: Msg, locale: str) -> str:
    if note_msg.key == "engine.ramp.blackout_risk":
        p = dict(note_msg.params)
        risk_val = str(p.get("risk", ""))
        if risk_val in ("low", "moderate", "high", "critical"):
            p["risk"] = t(f"engine.risk.{risk_val}", locale=locale)
        return t(note_msg.key, p, locale=locale)  # type: ignore[arg-type]
    return expand_msg(note_msg, locale=locale)


def _expand_cap_chain_notes(value: Msg, locale: str) -> str:
    raw = value.params.get("note_entries")
    if not raw:
        return str(value.params.get("notes", ""))
    entries = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(entries, list):
        return str(value.params.get("notes", ""))
    lines: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        note_msg = Msg(key=str(entry["k"]), params=dict(entry.get("p") or {}))
        note_text = _expand_ramp_note(note_msg, locale)
        lines.append(
            t(
                "engine.ramp.cap_chain_line",
                {
                    "factor": str(entry.get("factor", "")),
                    "note": note_text,
                    "ceiling": int(entry.get("ceiling", 0)),
                },
                locale=locale,
            )
        )
    return "; ".join(lines)


def _localize_summary_params(p: dict[str, Any], locale: str) -> dict[str, Any]:
    out = dict(p)
    order_raw = str(out.get("order", ""))
    if "," in order_raw:
        out["order"] = " > ".join(
            t(f"engine.priority.{part.strip()}", locale=locale)
            for part in order_raw.split(",")
            if part.strip()
        )
    risk_raw = str(out.get("risk", ""))
    if risk_raw in ("low", "moderate", "high", "critical"):
        out["risk"] = t(f"engine.risk.{risk_raw}", locale=locale)
    if out.get("has_mpc") == "yes":
        reserve = out.get("reserve")
        if reserve not in (None, ""):
            prefix = t(
                "engine.mpc.prefix_with_reserve",
                {"horizon": out.get("horizon", ""), "reserve": reserve},
                locale=locale,
            )
        else:
            prefix = t("engine.mpc.prefix", locale=locale)
        if out.get("survivable") == "yes":
            prefix += t("engine.mpc.survivable", locale=locale)
        else:
            prefix += t(
                "engine.mpc.not_survivable",
                {"kwh": out.get("kwh", "0")},
                locale=locale,
            )
        out["prefix"] = prefix
    if out.get("advisory_suffix") == "surplus":
        out["advisory_suffix"] = (
            " | "
            + t(
                "engine.advisory.surplus",
                {"kw": out.get("advisory_kw", 0)},
                locale=locale,
            )
        )
    else:
        out["advisory_suffix"] = ""
    out.setdefault("extra", "")
    out.setdefault("prefix", out.get("prefix", ""))
    return out


def expand_msg(value: Msg, *, locale: str | None = None) -> str:
    loc = locale or get_locale()
    if value.key in (
        "engine.summary.with_priorities_present",
        "engine.summary.with_priorities_absent",
    ):
        p = _localize_summary_params(dict(value.params), loc)
        return t(value.key, p, locale=loc)  # type: ignore[arg-type]
    if value.key in ("engine.grid.cap_chain", "engine.grid.cap_chain_below_threshold"):
        p = dict(value.params)
        p["notes"] = _expand_cap_chain_notes(value, loc)
        p.pop("note_entries", None)
        return t(value.key, p, locale=loc)  # type: ignore[arg-type]
    if value.key == "engine.reserve.main":
        p = dict(value.params)
        driver = p.get("driver", "")
        if isinstance(driver, str) and driver.startswith("engine."):
            p["driver"] = t(driver, locale=loc)
        hdh = float(p.get("hdh", 0) or 0)
        cdh = float(p.get("cdh", 0) or 0)
        p["extra_cold"] = (
            t("engine.reserve.cold_snap", {"hdh": int(hdh)}, locale=loc)
            if p.get("extra_cold") == "cold"
            else ""
        )
        p["extra_heat"] = (
            t("engine.reserve.heat_wave", {"cdh": int(cdh)}, locale=loc)
            if p.get("extra_heat") == "heat"
            else ""
        )
        p["extra_degraded"] = (
            t("engine.reserve.degraded_buffer", locale=loc)
            if p.get("extra_degraded") == "yes"
            else ""
        )
        return t(value.key, p, locale=loc)  # type: ignore[arg-type]
    return t(value.key, value.params, locale=loc)  # type: ignore[arg-type]


def msg_text(value: Msg | str | None, *, locale: str | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, Msg):
        return expand_msg(value, locale=locale)
    decoded = decode_msg(value)
    if isinstance(decoded, Msg):
        return expand_msg(decoded, locale=locale)
    return str(decoded)


def _is_msg_dict(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    keys = set(obj.keys())
    if keys <= {"k", "p"} and "k" in obj:
        return True
    return keys <= {"key", "params"} and "key" in obj


def _localize_value(value: Any, locale: str | None) -> Any:
    if isinstance(value, Msg):
        return value.text(locale=locale)
    if _is_msg_dict(value):
        k = value.get("k") or value.get("key")
        params = value.get("p") or value.get("params") or {}
        return t(str(k), dict(params), locale=locale)  # type: ignore[arg-type]
    return value


def _convert_datetime_value(value: str, site_tz: ZoneInfo) -> str:
    if not is_utc_serializable(value):
        return value
    return format_site_local_iso(parse_api_utc(value), site_tz)


def apply_site_timezone(obj: Any, site_tz: ZoneInfo) -> Any:
    """Recursively convert UTC ISO datetime strings to site-local ISO."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k in _DATETIME_KEYS and isinstance(v, str):
                out[k] = _convert_datetime_value(v, site_tz)
            else:
                out[k] = apply_site_timezone(v, site_tz)
        return out
    if isinstance(obj, list):
        return [apply_site_timezone(item, site_tz) for item in obj]
    return obj


def localize_payload(
    obj: Any,
    *,
    locale: str | None = None,
    site_tz: ZoneInfo | None = None,
) -> Any:
    """Walk JSON-like structures and resolve Msg dicts / add skip labels."""
    loc = locale or get_locale()
    if isinstance(obj, dict):
        # Explanation step objects (DecisionExplanation.steps entries).
        if "id" in obj and ("title_key" in obj or "detail_key" in obj):
            step = {
                k: localize_payload(v, locale=loc, site_tz=site_tz)
                for k, v in obj.items()
            }
            params = dict(step.get("params") or {})
            title_key = str(step.get("title_key") or "")
            detail_key = str(step.get("detail_key") or "")
            if title_key:
                step["title"] = t(title_key, params, locale=loc)  # type: ignore[arg-type]
            if detail_key:
                step["detail"] = t(detail_key, params, locale=loc)  # type: ignore[arg-type]
            if site_tz is not None:
                return apply_site_timezone(step, site_tz)
            return step
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k in _SKIP_FIELDS and isinstance(v, str):
                norm = normalize_skip_key(v) or v
                out[k] = norm
                out["skipped_reason_text"] = skip_reason_label(norm, locale=loc)
                continue
            if k == "degraded_reasons" and isinstance(v, list):
                out[k] = [
                    msg_text(item, locale=loc) if not isinstance(item, str) else item
                    for item in v
                ]
                continue
            if k == "reason" and (_is_msg_dict(v) or isinstance(v, Msg)):
                out[k] = msg_text(v, locale=loc)
                continue
            if k in ("rationale", "summary", "reserve_rationale") and (
                _is_msg_dict(v)
                or isinstance(v, Msg)
                or (isinstance(v, str) and v.startswith("{"))
            ):
                out[k] = msg_text(v, locale=loc)
                continue
            out[k] = localize_payload(v, locale=loc, site_tz=site_tz)
        result: Any = out
    elif isinstance(obj, list):
        result = [localize_payload(item, locale=loc, site_tz=site_tz) for item in obj]
    else:
        result = _localize_value(obj, loc)

    if site_tz is not None:
        return apply_site_timezone(result, site_tz)
    return result


def localize_model(
    model: Any,
    *,
    locale: str | None = None,
    site_tz: ZoneInfo | None = None,
) -> dict[str, Any]:
    dumped = model.model_dump(mode="json")
    return localize_payload(dumped, locale=locale, site_tz=site_tz)


def serialize_api_payload(
    obj: Any,
    *,
    locale: str | None = None,
    site_tz: ZoneInfo,
) -> Any:
    return localize_payload(obj, locale=locale, site_tz=site_tz)
