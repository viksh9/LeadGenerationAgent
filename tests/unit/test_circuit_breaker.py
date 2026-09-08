"""Circuit breaker unit tests (Prompt 40 §34)."""

from __future__ import annotations

import pytest

from resilience.circuit_breaker import CircuitBreaker, CircuitBreakerOpen, CircuitState


def test_opens_after_threshold_then_half_opens_then_closes():
    clock = [1000.0]
    cb = CircuitBreaker("t", failure_threshold=3, recovery_timeout=30, clock=lambda: clock[0])
    assert cb.state is CircuitState.CLOSED
    cb.record_failure(); cb.record_failure()
    assert cb.state is CircuitState.CLOSED and cb.allow()
    cb.record_failure()                       # threshold reached
    assert cb.state is CircuitState.OPEN and not cb.allow()
    clock[0] += 31                             # cooldown elapsed
    assert cb.state is CircuitState.HALF_OPEN and cb.allow()
    cb.record_success()
    assert cb.state is CircuitState.CLOSED


def test_half_open_failure_reopens():
    clock = [0.0]
    cb = CircuitBreaker("t", failure_threshold=1, recovery_timeout=10, clock=lambda: clock[0])
    cb.record_failure()
    assert cb.state is CircuitState.OPEN
    clock[0] += 11
    assert cb.state is CircuitState.HALF_OPEN
    cb.record_failure()                        # probe fails → reopen
    assert cb.state is CircuitState.OPEN


def test_call_short_circuits_when_open():
    clock = [0.0]
    cb = CircuitBreaker("t", failure_threshold=1, recovery_timeout=100, clock=lambda: clock[0])

    def boom():
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        cb.call(boom)                          # records failure → opens
    with pytest.raises(CircuitBreakerOpen):
        cb.call(lambda: 1)                     # short-circuited, underlying not called


def test_call_records_success():
    cb = CircuitBreaker("t", failure_threshold=2)
    assert cb.call(lambda: 42) == 42
    assert cb.state is CircuitState.CLOSED
