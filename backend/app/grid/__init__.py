"""Reactive grid handling + display-only statistics.

The grid is NEVER predicted. This module only: (a) computes opportunistic
top-up actions when the grid is physically present, and (b) summarises past
grid on/off behaviour for the dashboard. Stats never feed control decisions.
"""

from .reactive import ReactiveGrid

__all__ = ["ReactiveGrid"]
