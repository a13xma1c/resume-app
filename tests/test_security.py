"""Unit tests for CSRF helpers and the rate limiter."""

from __future__ import annotations

import threading

import pytest
from flask import Flask

from resumeapp.security import (
    CSRF_SESSION_KEY,
    RateLimiter,
    generate_csrf_token,
    validate_csrf_token,
)

# --- CSRF ----------------------------------------------------------------------


def test_generate_csrf_token_stores_in_session_and_is_idempotent(app: Flask) -> None:
    with app.test_request_context():
        from flask import session

        token = generate_csrf_token()
        assert session[CSRF_SESSION_KEY] == token
        assert generate_csrf_token() == token
        assert len(token) >= 32


def test_generate_csrf_token_is_unique_per_session(app: Flask) -> None:
    with app.test_request_context():
        first = generate_csrf_token()
    with app.test_request_context():
        second = generate_csrf_token()
    assert first != second


def test_validate_csrf_token(app: Flask) -> None:
    with app.test_request_context():
        token = generate_csrf_token()
        assert validate_csrf_token(token) is True
        assert validate_csrf_token(token + "x") is False
        assert validate_csrf_token(token[:-1]) is False
        assert validate_csrf_token("") is False
        assert validate_csrf_token(None) is False


def test_validate_csrf_token_without_session_token(app: Flask) -> None:
    with app.test_request_context():
        assert validate_csrf_token("anything") is False


def test_csrf_token_helper_available_in_templates(app: Flask) -> None:
    from flask import render_template_string, session

    with app.test_request_context():
        rendered = render_template_string("{{ csrf_token() }}")
        assert rendered == session[CSRF_SESSION_KEY]


# --- RateLimiter ---------------------------------------------------------------


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def test_allows_up_to_limit_then_blocks(clock: FakeClock) -> None:
    limiter = RateLimiter(3, 60, clock=clock)
    assert [limiter.hit("a") for _ in range(3)] == [True, True, True]
    assert limiter.hit("a") is False
    assert limiter.remaining("a") == 0


def test_blocked_hits_are_not_recorded(clock: FakeClock) -> None:
    limiter = RateLimiter(1, 60, clock=clock)
    assert limiter.hit("a")
    for _ in range(5):
        assert not limiter.hit("a")
    clock.advance(61)
    assert limiter.hit("a")  # window cleared even though we kept hammering


def test_window_slides(clock: FakeClock) -> None:
    limiter = RateLimiter(2, 10, clock=clock)
    assert limiter.hit("a")  # t=1000
    clock.advance(5)
    assert limiter.hit("a")  # t=1005
    assert not limiter.hit("a")
    clock.advance(5.1)  # t=1010.1 -> first hit expired
    assert limiter.hit("a")
    assert not limiter.hit("a")
    clock.advance(5)  # t=1015.1 -> second hit expired
    assert limiter.hit("a")


def test_keys_are_independent(clock: FakeClock) -> None:
    limiter = RateLimiter(1, 60, clock=clock)
    assert limiter.hit("a")
    assert limiter.hit("b")
    assert not limiter.hit("a")
    assert not limiter.hit("b")


def test_remaining(clock: FakeClock) -> None:
    limiter = RateLimiter(3, 60, clock=clock)
    assert limiter.remaining("a") == 3
    limiter.hit("a")
    assert limiter.remaining("a") == 2
    limiter.hit("a")
    limiter.hit("a")
    assert limiter.remaining("a") == 0
    clock.advance(61)
    assert limiter.remaining("a") == 3


def test_reset_single_key_and_all(clock: FakeClock) -> None:
    limiter = RateLimiter(1, 60, clock=clock)
    limiter.hit("a")
    limiter.hit("b")
    limiter.reset("a")
    assert limiter.hit("a")
    assert not limiter.hit("b")
    limiter.reset()
    assert limiter.hit("b")


def test_limit_zero_disables_limiting(clock: FakeClock) -> None:
    limiter = RateLimiter(0, 60, clock=clock)
    assert all(limiter.hit("a") for _ in range(1000))
    assert limiter.remaining("a") > 1_000_000


@pytest.mark.parametrize("limit,window", [(-1, 60), (1, 0), (1, -5)])
def test_invalid_parameters_rejected(limit: int, window: int) -> None:
    with pytest.raises(ValueError):
        RateLimiter(limit, window)


def test_default_clock_is_monotonic() -> None:
    limiter = RateLimiter(2, 60)
    assert limiter.hit("a")
    assert limiter.hit("a")
    assert not limiter.hit("a")


def test_thread_safety_under_contention() -> None:
    limiter = RateLimiter(50, 60)
    successes: list[bool] = []
    lock = threading.Lock()

    def worker() -> None:
        for _ in range(20):
            ok = limiter.hit("shared")
            with lock:
                successes.append(ok)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(successes) == 200
    assert sum(successes) == 50  # exactly the limit, never more


def test_idle_keys_are_swept(clock: FakeClock) -> None:
    limiter = RateLimiter(5, 10, clock=clock)
    for i in range(300):
        limiter.hit(f"client-{i}")
    assert len(limiter) <= 300
    clock.advance(11)  # everything expired
    for _ in range(RateLimiter.SWEEP_EVERY):
        limiter.hit("active")
    # The sweep ran: only the active key (and at most a few stragglers) remain.
    assert len(limiter) <= 2


def test_remaining_drops_expired_keys(clock: FakeClock) -> None:
    limiter = RateLimiter(2, 10, clock=clock)
    limiter.hit("a")
    assert len(limiter) == 1
    clock.advance(11)
    assert limiter.remaining("a") == 2
    assert len(limiter) == 0
    assert limiter.remaining("never-seen") == 2
    assert len(limiter) == 0


def test_sweep_keeps_live_entries(clock: FakeClock) -> None:
    limiter = RateLimiter(3, 100, clock=clock)
    limiter.hit("keep")
    limiter.hit("keep")
    for _ in range(RateLimiter.SWEEP_EVERY + 1):
        limiter.hit("other")
    assert limiter.remaining("keep") == 1
