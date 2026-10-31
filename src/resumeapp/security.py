"""Lightweight security helpers: CSRF tokens and request rate limiting."""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from flask import session

CSRF_SESSION_KEY = "_csrf_token"
CSRF_FORM_FIELD = "csrf_token"


def generate_csrf_token() -> str:
    """Return the session's CSRF token, creating one if needed."""
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf_token(submitted: str | None) -> bool:
    """Constant-time comparison of a submitted token with the session token."""
    expected = session.get(CSRF_SESSION_KEY)
    if not expected or not submitted:
        return False
    return hmac.compare_digest(expected, submitted)


class RateLimiter:
    """Sliding-window, in-memory rate limiter keyed by an arbitrary string.

    A ``limit`` of 0 disables limiting. Suitable for a single-process
    deployment; swap for a shared store if running several workers.
    """

    #: Sweep idle keys every this many recorded hits so the table cannot grow forever.
    SWEEP_EVERY = 256

    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        if limit < 0:
            raise ValueError("limit must be >= 0")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        self.limit = limit
        self.window = float(window_seconds)
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._since_sweep = 0

    def __len__(self) -> int:
        """Number of keys currently tracked (for monitoring and tests)."""
        with self._lock:
            return len(self._hits)

    def _prune(self, hits: deque[float], now: float) -> None:
        cutoff = now - self.window
        while hits and hits[0] <= cutoff:
            hits.popleft()

    def _sweep(self, now: float) -> None:
        """Drop keys whose hits have all expired (called with the lock held)."""
        cutoff = now - self.window
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]
        self._since_sweep = 0

    def hit(self, key: str) -> bool:
        """Record a request for ``key``. Returns True if it is within the limit."""
        if self.limit == 0:
            return True
        now = self._clock()
        with self._lock:
            self._since_sweep += 1
            if self._since_sweep >= self.SWEEP_EVERY:
                self._sweep(now)
            hits = self._hits[key]
            self._prune(hits, now)
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def remaining(self, key: str) -> int:
        """Number of requests ``key`` may still make in the current window."""
        if self.limit == 0:
            return 2**31 - 1
        now = self._clock()
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                self._hits.pop(key, None)
                return self.limit
            self._prune(hits, now)
            if not hits:
                del self._hits[key]
            return max(self.limit - len(hits), 0)

    def reset(self, key: str | None = None) -> None:
        """Forget recorded hits for ``key`` (or for everything when ``None``)."""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)
