"""Locale registry (mirrors frontend/src/locales/manifest.ts)."""

from __future__ import annotations

from typing import Literal

AppLocale = Literal["en", "ar", "fr"]

DEFAULT_LOCALE: AppLocale = "en"
SUPPORTED_LOCALES: tuple[AppLocale, ...] = ("en", "ar", "fr")

LOCALE_MATCH: dict[AppLocale, tuple[str, ...]] = {
    "en": ("en",),
    "ar": ("ar",),
    "fr": ("fr",),
}

LOCALE_NAMES: dict[AppLocale, str] = {
    "en": "English",
    "ar": "Arabic",
    "fr": "French",
}


def is_supported_locale(value: str) -> bool:
    return value in SUPPORTED_LOCALES


def resolve_locale(
    solar_locale: str | None,
    accept_language: str | None,
) -> AppLocale:
    """Pick locale from X-Solar-Locale, then Accept-Language, else en."""
    if solar_locale and is_supported_locale(solar_locale.strip().lower()):
        return solar_locale.strip().lower()  # type: ignore[return-value]
    if accept_language:
        for part in accept_language.split(","):
            token = part.split(";")[0].strip().lower()
            if not token:
                continue
            base = token.split("-")[0]
            for loc, prefixes in LOCALE_MATCH.items():
                if token in prefixes or base in prefixes:
                    return loc
    return DEFAULT_LOCALE
