"""Backend internationalization (mirrors frontend/src/i18n.ts)."""

from __future__ import annotations

import re
from contextvars import ContextVar, Token
import json
from typing import Any

from fastapi import HTTPException

from .catalog import get_messages
from .manifest import DEFAULT_LOCALE, LOCALE_NAMES, AppLocale, is_supported_locale, resolve_locale

locale_context: ContextVar[AppLocale] = ContextVar("locale", default=DEFAULT_LOCALE)

_SKIP_KEY_PREFIX = "engine.skip."
_REJECT_KEY_PREFIX = "engine.reject."

# Legacy English skip reasons stored in SQLite before i18n migration.
LEGACY_SKIP_MAP: dict[str, str] = {
    "capability not mapped": "engine.skip.capability_not_mapped",
    "HA stale; watchdog blocked write": "engine.skip.ha_stale",
    "shadow mode": "engine.skip.shadow_mode",
    "no shed snapshot; not restoring": "engine.skip.no_shed_snapshot",
    "was off before shed": "engine.skip.was_off_before_shed",
    "recently written (unchanged)": "engine.skip.recently_written",
    "already set": "engine.skip.already_set",
}


def get_locale() -> AppLocale:
    return locale_context.get()


def set_locale(locale: AppLocale) -> Token[AppLocale]:
    return locale_context.set(locale)


def reset_locale(token: Token[AppLocale]) -> None:
    locale_context.reset(token)


def resolve_request_locale(
    solar_locale: str | None,
    accept_language: str | None,
) -> AppLocale:
    return resolve_locale(solar_locale, accept_language)


def _get_nested(obj: dict[str, Any], key: str) -> str | None:
    parts = key.split(".")
    cur: Any = obj
    for part in parts:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur if isinstance(cur, str) else None


def _interpolate(
    template: str,
    params: dict[str, str | int | float] | None,
) -> str:
    if not params:
        return template

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        val = params.get(name)
        return str(val) if val is not None else match.group(0)

    return re.sub(r"\{(\w+)\}", repl, template)


def t(
    key: str,
    params: dict[str, str | int | float] | None = None,
    *,
    locale: AppLocale | None = None,
    fallback: str | None = None,
) -> str:
    loc = locale or get_locale()
    messages = get_messages(loc)
    raw = _get_nested(messages, key)
    if raw is None and loc != DEFAULT_LOCALE:
        raw = _get_nested(get_messages(DEFAULT_LOCALE), key)
    if raw is None:
        raw = fallback or key
    return _interpolate(raw, params)


def msg(key: str, /, **params: str | int | float):
    from ..models import Msg

    return Msg(key=key, params=dict(params))


def api_error(key: str, status_code: int, /, **params: str | int | float) -> HTTPException:
    return HTTPException(status_code=status_code, detail=t(key, params))


def format_validation_errors(errors: list[dict]) -> list[dict]:
    formatted: list[dict] = []
    for err in errors:
        loc = err.get("loc", ())
        loc_parts = [str(x) for x in loc if x not in ("body",)]
        loc_str = ".".join(loc_parts) or "body"
        raw_msg = str(err.get("msg", "invalid"))
        formatted.append(
            {
                "loc": list(loc),
                "msg": t("api.validation.field", {"loc": loc_str, "msg": raw_msg}),
            }
        )
    return formatted


def normalize_skip_key(reason: str | None) -> str | None:
    if reason is None:
        return None
    text = reason.strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return reason
        if isinstance(data, dict) and "k" in data:
            return str(data["k"])
        if isinstance(data, dict) and "key" in data:
            return str(data["key"])
    if text.startswith(_SKIP_KEY_PREFIX) or text.startswith(_REJECT_KEY_PREFIX):
        return text
    if text in LEGACY_SKIP_MAP:
        return LEGACY_SKIP_MAP[text]
    if text.startswith("hard-bound reject: "):
        return "engine.skip.hard_bound_reject"
    if text.startswith("rate-limited ("):
        return "engine.skip.rate_limited"
    return text


def skip_reason_label(reason: str | None, *, locale: AppLocale | None = None) -> str | None:
    if reason is None:
        return None
    text = reason.strip()
    params: dict[str, str | int | float] | None = None
    key: str | None = None
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return reason
        if isinstance(data, dict) and "k" in data:
            key = str(data["k"])
            params = dict(data.get("p") or {})
        elif isinstance(data, dict) and "key" in data:
            key = str(data["key"])
            params = dict(data.get("params") or {})
    if key is None:
        key = normalize_skip_key(text)
    if key and (key.startswith(_SKIP_KEY_PREFIX) or key.startswith(_REJECT_KEY_PREFIX)):
        if key == "engine.skip.hard_bound_reject" and text.startswith("hard-bound reject: "):
            return t(key, {"detail": text[len("hard-bound reject: ") :]}, locale=locale)
        if key == "engine.skip.rate_limited" and text.startswith("rate-limited ("):
            m = re.match(r"rate-limited \((\d+)s < (\d+)s\)", text)
            if m:
                return t(
                    key,
                    {"elapsed": int(m.group(1)), "min": int(m.group(2))},
                    locale=locale,
                )
        if params is not None:
            return t(key, params, locale=locale)
        return t(key, locale=locale)
    return reason


__all__ = [
    "DEFAULT_LOCALE",
    "LOCALE_NAMES",
    "LEGACY_SKIP_MAP",
    "AppLocale",
    "api_error",
    "format_validation_errors",
    "get_locale",
    "is_supported_locale",
    "locale_context",
    "msg",
    "normalize_skip_key",
    "reset_locale",
    "resolve_request_locale",
    "set_locale",
    "skip_reason_label",
    "t",
]
