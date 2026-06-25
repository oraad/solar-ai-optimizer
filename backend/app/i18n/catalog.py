"""Load JSON locale catalogs."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .manifest import DEFAULT_LOCALE, AppLocale

_LOCALES_DIR = Path(__file__).resolve().parent / "locales"


@lru_cache(maxsize=8)
def get_messages(locale: AppLocale) -> dict[str, Any]:
    path = _LOCALES_DIR / f"{locale}.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)
