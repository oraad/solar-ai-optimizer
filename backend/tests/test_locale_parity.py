"""Locale catalog key parity vs en.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

LOCALES_DIR = Path(__file__).resolve().parents[1] / "app" / "i18n" / "locales"


def _leaf_keys(obj: Any, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys |= _leaf_keys(v, path)
            else:
                keys.add(path)
    return keys


def test_locale_parity_with_english():
    with (LOCALES_DIR / "en.json").open(encoding="utf-8") as f:
        en = json.load(f)
    en_keys = _leaf_keys(en)
    for locale in ("ar", "fr"):
        with (LOCALES_DIR / f"{locale}.json").open(encoding="utf-8") as f:
            data = json.load(f)
        assert _leaf_keys(data) == en_keys, f"{locale} keys differ from en"
