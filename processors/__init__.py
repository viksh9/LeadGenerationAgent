"""Processors package.

Note: ``AnalysisPipeline`` lives in ``processors.analysis_pipeline`` and is
imported from there directly (``from processors.analysis_pipeline import
AnalysisPipeline``). It is intentionally NOT re-exported here — it depends on the
API/database layers, and the intelligence engines import ``processors.normalizer``,
so eagerly importing the pipeline from this package ``__init__`` would create an
import cycle.
"""

from processors.normalizer import NormalizedLead, normalize_record

__all__ = ["NormalizedLead", "normalize_record"]
