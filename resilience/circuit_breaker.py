"""A minimal, thread-safe circuit breaker (§34).

States: CLOSED (normal) → OPEN (failing; calls short-circuit) → HALF_OPEN (a
probe is allowed after a cooldown) → CLOSED on success / OPEN on failure. The
clock is injectable for deterministic tests. This never fabricates a result — a
caller that is short-circuited must fall back to its own deterministic path
(e.g. the deterministic AI baseline), not to fake data.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpen(RuntimeError):
    """Raised by ``call()`` when the breaker is OPEN and the call is short-circuited."""


@dataclass
class _Clock:
    def now(self) -> float:
        import time
        return time.monotonic()


class CircuitBreaker:
    def __init__(self, name: str, *, failure_threshold: int = 5, recovery_timeout: float = 60.0,
                 clock: Callable[[], float] | None = None):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._clock = clock or _Clock().now
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._recompute_state()

    def _recompute_state(self) -> CircuitState:
        if self._state is CircuitState.OPEN and (self._clock() - self._opened_at) >= self.recovery_timeout:
            self._state = CircuitState.HALF_OPEN
        return self._state

    def allow(self) -> bool:
        """Whether a call may proceed right now."""
        with self._lock:
            return self._recompute_state() is not CircuitState.OPEN

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._state is CircuitState.HALF_OPEN or self._failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()

    def call(self, fn: Callable, *args, **kwargs):
        """Run ``fn`` through the breaker. Raises CircuitBreakerOpen if short-circuited;
        records success/failure otherwise and re-raises the underlying exception."""
        if not self.allow():
            raise CircuitBreakerOpen(f"circuit '{self.name}' is OPEN")
        try:
            result = fn(*args, **kwargs)
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result

    def snapshot(self) -> dict:
        with self._lock:
            return {"name": self.name, "state": self._recompute_state().value, "failures": self._failures}


_REGISTRY: dict[str, CircuitBreaker] = {}
_REG_LOCK = threading.Lock()


def get_breaker(name: str, *, failure_threshold: int = 5, recovery_timeout: float = 60.0) -> CircuitBreaker:
    with _REG_LOCK:
        breaker = _REGISTRY.get(name)
        if breaker is None:
            breaker = CircuitBreaker(name, failure_threshold=failure_threshold,
                                     recovery_timeout=recovery_timeout)
            _REGISTRY[name] = breaker
        return breaker


def all_breaker_states() -> list[dict]:
    with _REG_LOCK:
        return [b.snapshot() for b in _REGISTRY.values()]


def reset_all_breakers() -> None:
    """Test helper — clears breaker state between tests."""
    with _REG_LOCK:
        _REGISTRY.clear()
