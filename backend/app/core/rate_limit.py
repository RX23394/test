"""In-process fixed-window rate limiting.

The application runs as a single process in both the documented local setup and
the bundled Compose file, so a small in-memory limiter is enough to stop
password guessing and request floods. A multi-worker deployment must move this
to a shared store (or put a gateway in front), which is stated in the README.
"""

import threading
import time
from collections import deque
from collections.abc import Callable
from functools import lru_cache

from fastapi import Request

from app.core.config import get_settings


class FixedWindowRateLimiter:
    """Count events per key inside a sliding time window."""

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialize the limiter with its limit and window length."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._limit = limit
        self._window_seconds = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        """Record one event and report whether it stays inside the limit."""
        now = self._clock()
        with self._lock:
            events = self._recent_events(key, now)
            if len(events) >= self._limit:
                return False
            events.append(now)
            return True

    def retry_after(self, key: str) -> float:
        """Return the seconds until the oldest event leaves the window."""
        now = self._clock()
        with self._lock:
            events = self._recent_events(key, now)
            if len(events) < self._limit:
                return 0.0
            return max(0.0, self._window_seconds - (now - events[0]))

    def reset(self, key: str) -> None:
        """Forget recorded events, for example after a successful login."""
        with self._lock:
            self._events.pop(key, None)

    def _recent_events(self, key: str, now: float) -> deque[float]:
        """Return the key's events inside the window, dropping the rest."""
        events = self._events.setdefault(key, deque())
        cutoff = now - self._window_seconds
        while events and events[0] <= cutoff:
            events.popleft()
        if not events and key in self._events:
            # Keep the mapping small: idle keys do not need an empty deque.
            self._events.pop(key, None)
            events = self._events.setdefault(key, deque())
        return events


@lru_cache(maxsize=1)
def get_login_rate_limiter() -> FixedWindowRateLimiter:
    """Return the process-wide login attempt limiter."""
    settings = get_settings()
    return FixedWindowRateLimiter(
        settings.login_max_attempts,
        settings.login_window_seconds,
    )


@lru_cache(maxsize=1)
def get_chat_rate_limiter() -> FixedWindowRateLimiter:
    """Return the process-wide chat request limiter."""
    settings = get_settings()
    return FixedWindowRateLimiter(
        settings.chat_max_requests,
        settings.chat_window_seconds,
    )


def client_key(request: Request, identifier: str) -> str:
    """Build a limiter key from the client address and a login identifier."""
    client_host = request.client.host if request.client is not None else "unknown"
    return f"{client_host}:{identifier.strip().lower()}"
