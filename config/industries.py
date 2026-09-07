"""Target-industry configuration for real-data collection.

Kept separate from individual collectors so industry focus can evolve without
touching collection code. Industry normalization (mapping raw source industry
strings onto these canonical segments) is a later step — only the foundation and
canonical list live here.
"""

from __future__ import annotations

# The production system focuses on the IT industry.
PRIMARY_INDUSTRY = "IT"

# Canonical IT segments we care about for demand signals.
IT_SEGMENTS: tuple[str, ...] = (
    "IT Services",
    "IT Consulting",
    "Software",
    "SaaS",
    "Cloud",
    "Cybersecurity",
    "FinTech Technology",
    "HealthTech",
    "AI/ML",
    "Data/Analytics",
    "E-commerce Technology",
    "Enterprise Software",
    "Digital Transformation",
)

# Lower-cased alias hints used by a FUTURE industry normalizer (not applied here).
IT_SEGMENT_ALIASES: dict[str, tuple[str, ...]] = {
    "IT Services": ("it services", "technology services", "software services"),
    "IT Consulting": ("it consulting", "technology consulting"),
    "Software": ("software", "software development", "product engineering"),
    "SaaS": ("saas", "software as a service"),
    "Cloud": ("cloud", "cloud computing"),
    "Cybersecurity": ("cybersecurity", "information security", "infosec"),
    "FinTech Technology": ("fintech", "financial technology"),
    "HealthTech": ("healthtech", "health tech", "healthcare technology"),
    "AI/ML": ("ai", "artificial intelligence", "machine learning", "ml"),
    "Data/Analytics": ("data", "analytics", "data engineering"),
    "E-commerce Technology": ("e-commerce", "ecommerce", "commerce technology"),
    "Enterprise Software": ("enterprise software", "erp", "crm"),
    "Digital Transformation": ("digital transformation", "modernization"),
}


def is_it_segment(segment: str) -> bool:
    """True if `segment` is one of the canonical IT segments (case-insensitive)."""
    return segment.strip().lower() in {s.lower() for s in IT_SEGMENTS}
