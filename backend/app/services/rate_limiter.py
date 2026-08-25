from __future__ import annotations

import time
from collections import defaultdict


class FixedWindowRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, limit: int, window_seconds: int) -> int | None:
        now = time.monotonic()
        timestamps = [
            timestamp
            for timestamp in self._requests[key]
            if now - timestamp < window_seconds
        ]
        self._requests[key] = timestamps
        if len(timestamps) >= limit:
            return max(1, int(window_seconds - (now - timestamps[0]) + 0.999))
        timestamps.append(now)
        return None

    def clear(self) -> None:
        self._requests.clear()


auth_rate_limiter = FixedWindowRateLimiter()