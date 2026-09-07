"""Real-data collection package.

This package holds the SOURCE REGISTRY, COLLECTOR INTERFACE, and raw-record
utilities that later phases build real collectors on top of. It performs NO
external network requests itself — see docs/data-source-architecture.md.

No source is considered connected until its collector is implemented, tested,
and verified.
"""
