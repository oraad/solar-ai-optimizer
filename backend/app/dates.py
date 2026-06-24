"""Flexible datetime parsing for forecast ingestion and future API inputs."""

from __future__ import annotations

import re
from datetime import datetime

from dateutil import parser as dtparser

_ISO_DATE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})"
    r"(?:[T\s](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?(?:Z|[+-]\d{2}:?\d{2})?)?$"
)
_DAY_FIRST = (
    "%d/%m/%y",
    "%d/%m/%Y",
    "%d-%m-%y",
    "%d-%m-%Y",
    "%d/%m/%y %H:%M",
    "%d/%m/%Y %H:%M",
    "%d/%m/%y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%d-%m-%y %H:%M",
    "%d-%m-%Y %H:%M",
    "%d-%m-%y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
)


def parse_datetime(value: str, *, day_first: bool = True) -> datetime:
    """Parse a datetime string (ISO, DD/MM/YY, or dateutil fallback)."""
    text = value.strip()
    if not text:
        raise ValueError("empty datetime string")

    if _ISO_DATE.match(text):
        normalized = text.replace("Z", "+00:00")
        if "T" not in normalized and " " not in normalized:
            normalized = f"{normalized}T00:00:00"
        elif " " in normalized and "T" not in normalized:
            normalized = normalized.replace(" ", "T", 1)
        return datetime.fromisoformat(normalized)

    if day_first:
        for fmt in _DAY_FIRST:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue

    return dtparser.parse(text, dayfirst=day_first)
