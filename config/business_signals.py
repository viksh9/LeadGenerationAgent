"""Configuration for business-signal detection (keywords, value parsing, mapping).

Keyword sets and thresholds live here so tuning never touches detection code.
Reuses the existing SignalType for Lead integration — BusinessSignalType maps
onto it rather than duplicating the lead signal enum.
"""

from __future__ import annotations

from database.models import BusinessSignalType, SignalType

# Ordered most-specific-first: the detector returns the first type whose keywords
# appear. Keywords are lowercase substrings matched against title+description.
BUSINESS_SIGNAL_KEYWORDS: tuple[tuple[BusinessSignalType, tuple[str, ...]], ...] = (
    (BusinessSignalType.TENDER, (
        "tender", "request for proposal", "rfp", "request for quotation", "rfq",
        "expression of interest", " eoi", "procurement notice", "bid document",
    )),
    (BusinessSignalType.CONTRACT, (
        "contract awarded", "awarded a contract", "wins contract", "won the contract",
        "bags contract", "master services agreement", "statement of work", " sow ",
        "services agreement", "it services contract", "software contract", "signs contract",
    )),
    (BusinessSignalType.PROJECT_AWARD, (
        "project awarded", "awarded the project", "wins project", "bags project",
        "won a project", "selected to implement", "chosen to build", "to implement",
    )),
    (BusinessSignalType.DELIVERY_CENTER_EXPANSION, (
        "delivery center", "delivery centre", "global capability center", "gcc",
        "development center", "development centre", "new center", "new centre",
        "innovation center", "innovation centre",
    )),
    (BusinessSignalType.ENGINEERING_EXPANSION, (
        "engineering center", "engineering centre", "engineering team", "r&d center",
        "expand engineering", "engineering hub", "tech hub", "scaling engineering",
    )),
    (BusinessSignalType.CLOUD_MIGRATION, (
        "cloud migration", "migrate to cloud", "cloud transformation", "moving to the cloud",
        "aws migration", "azure migration", "cloud adoption",
    )),
    (BusinessSignalType.AI_INITIATIVE, (
        "ai initiative", "artificial intelligence", "generative ai", "gen ai", "genai",
        "machine learning platform", "ai platform", "ai transformation", "ai program",
    )),
    (BusinessSignalType.DIGITAL_TRANSFORMATION, (
        "digital transformation", "digitalisation", "digitalization", "digital initiative",
        "digital program", "digital overhaul", "digital journey",
    )),
    (BusinessSignalType.TECHNOLOGY_MODERNIZATION, (
        "modernization", "modernisation", "legacy modernization", "application modernization",
        "platform modernization", "technology upgrade", "re-platforming", "replatforming",
    )),
    (BusinessSignalType.OUTSOURCING, (
        "outsourcing", "outsourced", "managed services", "it outsourcing", "bpo deal",
    )),
    (BusinessSignalType.VENDOR_REQUIREMENT, (
        "staff augmentation", "staffing partner", "technology partner required",
        "seeking vendor", "vendor requirement", "system integrator", "implementation partner",
    )),
    (BusinessSignalType.PARTNERSHIP, (
        "partnership", "partners with", "strategic partnership", "collaborates with",
        "joins hands", "alliance", "teams up with",
    )),
    (BusinessSignalType.ACQUISITION, (
        "acquires", "acquisition", "to acquire", "acquired by", "merger", "buyout", "takeover",
    )),
    (BusinessSignalType.EXPANSION, (
        "expansion", "expands operations", "new office", "opens office", "to open", "sets up",
        "new facility", "invest", "investment",
    )),
    (BusinessSignalType.PROJECT_EXECUTION, (
        "implementation", "rollout", "go-live", "deployment", "system integration", "deploying",
    )),
)

# Map business signals onto the existing Lead SignalType for lead integration.
BUSINESS_TO_LEAD_SIGNAL: dict[BusinessSignalType, SignalType] = {
    BusinessSignalType.PROJECT_AWARD: SignalType.PROJECT_AWARD,
    BusinessSignalType.PROJECT_EXECUTION: SignalType.PROJECT_EXECUTION,
    BusinessSignalType.CONTRACT: SignalType.CONTRACT,
    BusinessSignalType.TENDER: SignalType.PROJECT_AWARD,
    BusinessSignalType.DIGITAL_TRANSFORMATION: SignalType.DIGITAL_TRANSFORMATION,
    BusinessSignalType.CLOUD_MIGRATION: SignalType.DIGITAL_TRANSFORMATION,
    BusinessSignalType.TECHNOLOGY_MODERNIZATION: SignalType.TECHNOLOGY_INITIATIVE,
    BusinessSignalType.AI_INITIATIVE: SignalType.TECHNOLOGY_INITIATIVE,
    BusinessSignalType.PARTNERSHIP: SignalType.CONTRACT,
    BusinessSignalType.EXPANSION: SignalType.EXPANSION,
    BusinessSignalType.DELIVERY_CENTER_EXPANSION: SignalType.EXPANSION,
    BusinessSignalType.ENGINEERING_EXPANSION: SignalType.EXPANSION,
    BusinessSignalType.VENDOR_REQUIREMENT: SignalType.VENDOR_REQUIREMENT,
    BusinessSignalType.OUTSOURCING: SignalType.VENDOR_REQUIREMENT,
    BusinessSignalType.ACQUISITION: SignalType.OTHER,
    BusinessSignalType.OTHER: SignalType.OTHER,
}

# Signal types that, on their own, are stronger opportunity indicators.
STRONG_SIGNAL_TYPES: frozenset[BusinessSignalType] = frozenset({
    BusinessSignalType.PROJECT_AWARD, BusinessSignalType.CONTRACT, BusinessSignalType.TENDER,
    BusinessSignalType.DELIVERY_CENTER_EXPANSION, BusinessSignalType.CLOUD_MIGRATION,
})

# Obvious non-IT-business noise (dropped from relevance unless IT evidence present).
IRRELEVANT_TERMS: tuple[str, ...] = (
    "cricket", "football", "sports", "bollywood", "box office", "celebrity",
    "weather", "horoscope", "recipe", "election result", "share price target",
)

# Currency multipliers (Indian + international units).
VALUE_MULTIPLIERS: dict[str, float] = {
    "crore": 1e7, "cr": 1e7, "crores": 1e7,
    "lakh": 1e5, "lakhs": 1e5, "lac": 1e5,
    "billion": 1e9, "bn": 1e9,
    "million": 1e6, "mn": 1e6, "mil": 1e6,
    "thousand": 1e3, "k": 1e3,
}

# Source confidence (0-100) by source_id — official/government high, aggregators lower.
BUSINESS_SOURCE_CONFIDENCE: dict[str, int] = {
    "company_newsroom": 90,
    "government_open_data": 90,
    "government_procurement": 90,
    "stock_exchange_announcements": 85,
    "business_news": 65,
    "technology_news": 60,
    "rss_news": 55,
    "demo_business": 60,
}
DEFAULT_BUSINESS_SOURCE_CONFIDENCE = 45
