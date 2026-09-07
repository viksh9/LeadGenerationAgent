"""Scheduler error taxonomy driving the retry policy (§23)."""

from __future__ import annotations


class SchedulerError(RuntimeError):
    """Base scheduler error."""


class TransientJobError(SchedulerError):
    """A recoverable failure (timeout, temporary 5xx, rate limit). Retried with
    backoff up to the job's max_retries."""


class PermanentJobError(SchedulerError):
    """A non-recoverable failure (invalid credentials, permanent 4xx,
    unsupported/licensing-disabled source). NEVER retried (§23)."""


class SkipJob(SchedulerError):
    """The job legitimately has nothing to do this cycle (e.g. source
    NOT_CONFIGURED, budget exhausted, or lock held). Recorded as SKIPPED, not a
    failure, and never fabricates results."""
