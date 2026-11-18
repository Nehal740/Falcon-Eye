"""A small in-memory sliding-window rate limiter.

Good for a single backend process (development, small deployments). If you
run several backend replicas, replace this with a shared store such as Redis
- see docs/KNOWN_LIMITATIONS.md.
"""

from __future__ import annotations

import threading
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def hit(self, key: str, limit: int, window_seconds: int,
            now: float | None = None) -> tuple[bool, int]:
        """Record a hit. Returns ``(allowed, retry_after_seconds)``."""
        now = time.monotonic() if now is None else now
        with self._lock:
            self._sweep(now, window_seconds)
            bucket = self._hits.setdefault(key, deque())
            cutoff = now - window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry = max(1, int(bucket[0] + window_seconds - now) + 1)
                return False, retry
            bucket.append(now)
            return True, 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()

    def _sweep(self, now: float, window_seconds: int) -> None:
        # Drop idle buckets now and then so memory cannot grow forever.
        if now - self._last_sweep < 60:
            return
        self._last_sweep = now
        stale = [k for k, b in self._hits.items()
                 if not b or b[-1] <= now - max(window_seconds, 3600)]
        for key in stale:
            del self._hits[key]


limiter = SlidingWindowLimiter()
