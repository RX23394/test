"""Tests for the in-process fixed-window rate limiter."""

from types import SimpleNamespace

import pytest

from app.core.rate_limit import FixedWindowRateLimiter, client_key


class FakeClock:
    """Provide a manually advanced monotonic clock."""

    def __init__(self) -> None:
        """Start the clock at zero."""
        self.now = 0.0

    def __call__(self) -> float:
        """Return the current fake time."""
        return self.now

    def advance(self, seconds: float) -> None:
        """Move the clock forward."""
        self.now += seconds


def test_limiter_allows_events_up_to_the_limit() -> None:
    """The limit-th event is allowed and the next one is rejected."""
    limiter = FixedWindowRateLimiter(limit=3, window_seconds=60)

    assert [limiter.allow("user") for _ in range(3)] == [True, True, True]
    assert limiter.allow("user") is False


def test_limiter_separates_keys() -> None:
    """One key exhausting its budget does not limit another key."""
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60)

    assert limiter.allow("first") is True
    assert limiter.allow("first") is False
    assert limiter.allow("second") is True


def test_limiter_forgets_events_after_the_window() -> None:
    """Events older than the window no longer count and Retry-After shrinks."""
    clock = FakeClock()
    limiter = FixedWindowRateLimiter(limit=2, window_seconds=30, clock=clock)
    assert limiter.allow("user") is True
    assert limiter.allow("user") is True
    assert limiter.allow("user") is False
    assert limiter.retry_after("user") == pytest.approx(30.0)

    clock.advance(20)
    assert limiter.retry_after("user") == pytest.approx(10.0)
    assert limiter.allow("user") is False

    clock.advance(11)
    assert limiter.allow("user") is True
    assert limiter.retry_after("user") == 0.0


def test_limiter_reset_clears_recorded_events() -> None:
    """A successful login clears the failed attempts recorded before it."""
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60)
    assert limiter.allow("user") is True
    assert limiter.allow("user") is False

    limiter.reset("user")

    assert limiter.allow("user") is True


def test_limiter_leaves_no_empty_keys_behind() -> None:
    """Fully expired keys are dropped instead of accumulating forever."""
    clock = FakeClock()
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=10, clock=clock)
    assert limiter.allow("user") is True

    clock.advance(11)
    assert limiter.allow("user") is True
    assert len(limiter._events) == 1  # noqa: SLF001 - asserts internal cleanup


@pytest.mark.parametrize(
    ("limit", "window_seconds"),
    [(0, 60), (-1, 60), (1, 0), (1, -5)],
)
def test_limiter_rejects_invalid_configuration(
    limit: int,
    window_seconds: float,
) -> None:
    """A non-positive limit or window is a programming error."""
    with pytest.raises(ValueError):
        FixedWindowRateLimiter(limit=limit, window_seconds=window_seconds)


def test_client_key_normalizes_identifier_and_uses_client_address() -> None:
    """Keys combine the client address with a normalized login identifier."""

    class FakeRequest:
        """Minimal request double exposing only the client address."""

        def __init__(self) -> None:
            """Attach a client address holder."""
            self.client = SimpleNamespace(host="10.0.0.7")

    assert client_key(FakeRequest(), "  Admin ") == "10.0.0.7:admin"


def test_client_key_handles_a_missing_client_address() -> None:
    """A request without a client address still produces a stable key."""

    class FakeRequest:
        """Minimal request double without a client."""

        client = None

    assert client_key(FakeRequest(), "admin") == "unknown:admin"
