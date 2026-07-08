"""Shared pytest hooks and guards."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from app.models import Msg

# Placeholder Msg for tests that do not assert on rationale/reason text.
DUMMY_MSG = Msg(key="")

if sys.version_info < (3, 14):
    raise RuntimeError(
        f"Python 3.14+ required; got {sys.version}. "
        "Use: docker compose run --rm test"
    )


def wire_orchestrator_site_tz(orch: MagicMock, tz_name: str = "UTC") -> None:
    """Give MagicMock orchestrators a real ZoneInfo for API site-timezone serialization."""
    orch.forecast.site_tz.return_value = ZoneInfo(tz_name)
