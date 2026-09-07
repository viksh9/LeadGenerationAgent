"""Notification / alerting layer (§26–§33).

Turns REAL monitoring Findings into in-app ``Alert`` rows after applying user
preferences, deterministic severity, provenance gating, and deduplication.
Business alerts require REAL provenance; source-health alerts are operational.
External channels (email/Slack/webhook) are interface-only until explicitly
configured — nothing is ever sent externally by default (§30).
"""
