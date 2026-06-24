"""Shared pytest hooks and guards."""

from __future__ import annotations

import sys

if sys.version_info < (3, 14):
    raise RuntimeError(
        f"Python 3.14+ required; got {sys.version}. "
        "Use: docker compose run --rm test"
    )
