"""Runtime capability probes (optional dependencies)."""

from __future__ import annotations


def mpc_available() -> bool:
    try:
        import pulp  # noqa: F401

        return True
    except ImportError:
        return False


def ml_available() -> bool:
    try:
        import numpy  # noqa: F401
        import sklearn  # noqa: F401

        return True
    except ImportError:
        return False
