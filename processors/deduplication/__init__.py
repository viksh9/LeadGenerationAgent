"""Cross-source job deduplication.

Identifies the SAME real Indian IT job across multiple legitimate sources, counts
it once as a canonical JobRecord, and preserves EVERY source as a
JobSourceReference (evidence). Deterministic, explainable, no LLM/network.

Reuses the existing JobRecord / JobSourceReference models. This layer does not do
evidence verification (a later stage).
"""

from processors.deduplication.job_deduplicator import (  # noqa: F401
    DEDUPLICATION_VERSION,
    DedupSummary,
    JobDeduplicationService,
)
