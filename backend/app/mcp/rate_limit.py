"""In-memory per-key rate limiting for MCP and debug endpoints."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class _Bucket:
    window_start: float = 0.0
    count: int = 0


@dataclass
class RateLimiter:
    """Simple fixed-window rate limiter."""

    limits: dict[str, tuple[int, int]] = field(default_factory=dict)
    _buckets: dict[str, _Bucket] = field(default_factory=dict)

    def allow(self, key: str, category: str) -> bool:
        limit, window_secs = self.limits.get(category, (60, 60))
        now = time.monotonic()
        bucket_key = f"{key}:{category}"
        bucket = self._buckets.get(bucket_key)
        if bucket is None or now - bucket.window_start >= window_secs:
            self._buckets[bucket_key] = _Bucket(window_start=now, count=1)
            return True
        if bucket.count >= limit:
            return False
        bucket.count += 1
        return True


DEFAULT_LIMITS: dict[str, tuple[int, int]] = {
    "simulate": (10, 60),
    "write": (5, 60),
    "read": (60, 60),
}

rate_limiter = RateLimiter(limits=DEFAULT_LIMITS)
