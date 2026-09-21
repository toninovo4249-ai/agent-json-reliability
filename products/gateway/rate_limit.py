from __future__ import annotations

import time
from collections import defaultdict


class RateLimiter:
    def __init__(self, per_minute: int = 120, burst: int = 20):
        self.per_minute = per_minute
        self.burst = burst
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str, now: float | None = None) -> bool:
        t = now if now is not None else time.time()
        window = [x for x in self._hits[key] if t - x < 60.0]
        if len(window) >= self.per_minute:
            self._hits[key] = window
            return False
        # burst: more than `burst` in 2 seconds
        burst_n = sum(1 for x in window if t - x < 2.0)
        if burst_n >= self.burst:
            self._hits[key] = window
            return False
        window.append(t)
        self._hits[key] = window
        return True
