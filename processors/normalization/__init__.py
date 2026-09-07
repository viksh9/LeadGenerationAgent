"""Real-data normalization engine.

Turns messy multi-source real data into a reliable canonical representation
WITHOUT losing original source evidence. Every normalizer is a pure, deterministic
function (no network, no LLM, no DB) and always keeps the original value alongside
the normalized one.

This layer does NOT perform cross-source deduplication, company merging, signal
detection, or lead scoring — those are separate stages.
"""

from processors.normalization.normalizer import (  # noqa: F401
    NORMALIZATION_VERSION,
    JobNormalizer,
    normalize_job,
    normalize_many,
)
from processors.normalization.result import NormalizedJobRecord  # noqa: F401
