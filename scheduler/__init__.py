"""Scheduling layer (Prompt 38).

A lightweight, in-process, deterministic scheduler over the existing pipeline.
It orchestrates the real collectors and monitoring detectors on configurable
intervals; it never reimplements ingestion. The background runner is OFF unless
``SCHEDULER_ENABLED`` is set, so imports/tests/CI never spawn threads or make
network calls.
"""
