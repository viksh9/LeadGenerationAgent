"""Resilience primitives (Prompt 40 §33, §34): circuit breaking for unstable
external providers so the platform degrades gracefully instead of hammering a
failing dependency. Deterministic core intelligence always keeps working."""

from resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
    get_breaker,
    reset_all_breakers,
)

__all__ = [
    "CircuitBreaker", "CircuitBreakerOpen", "CircuitState", "get_breaker", "reset_all_breakers",
]
