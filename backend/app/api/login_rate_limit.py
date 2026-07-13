"""In-process sliding-window rate limit for local admin login."""

from __future__ import annotations

import threading
import time

_lock = threading.Lock()
# ip -> list of failure timestamps
_failures: dict[str, list[float]] = {}

# 5 failures per 5 minutes per IP
MAX_FAILURES = 5
WINDOW_SECONDS = 300


def _prune(bucket: list[float], now: float) -> list[float]:
    cutoff = now - WINDOW_SECONDS
    return [t for t in bucket if t > cutoff]


def login_allowed(ip: str) -> bool:
    now = time.time()
    with _lock:
        bucket = _prune(_failures.get(ip, []), now)
        _failures[ip] = bucket
        return len(bucket) < MAX_FAILURES


def record_login_failure(ip: str) -> None:
    now = time.time()
    with _lock:
        bucket = _prune(_failures.get(ip, []), now)
        bucket.append(now)
        _failures[ip] = bucket


def clear_login_failures(ip: str) -> None:
    with _lock:
        _failures.pop(ip, None)


def retry_after_seconds(ip: str) -> int:
    now = time.time()
    with _lock:
        bucket = _prune(_failures.get(ip, []), now)
        if len(bucket) < MAX_FAILURES:
            return 0
        oldest = min(bucket)
        return max(1, int(WINDOW_SECONDS - (now - oldest)) + 1)
