"""Company-level aggregation engine.

Turns individual IT job postings (raw source records) into ONE company-level
hiring opportunity per company: counts, recency, technology demand, roles,
cities, hiring intensity, business signals, evidence, and classification.

This is the core of the sales-intelligence pipeline: a single company with 40
technology openings is ONE lead, not 40. Pure/deterministic given `now` — no DB,
no network — so it is fully unit-testable.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from config.aggregation import DEFAULT_AGGREGATION_CONFIG, AggregationConfig
from collectors.raw_record import normalize_company_name
from database.models import CompanyType, DataProvenance, HiringIntensity, SignalType
from ingestion.extract import extract_roles, extract_technologies

# Title tokens that indicate a senior/decision-influencing role.
_SENIORITY_TOKENS = (
    "senior", "sr.", "lead", "principal", "staff", "architect", "manager",
    "head", "director", "vp", "chief", "cto",
)
_VENDOR_TOKENS = ("contract", "contractor", "staff augmentation", "staffing", "vendor", "c2h", "temporary")
_CLOUD_TECHS = {"AWS", "Azure", "GCP", "Kubernetes", "Docker", "DevOps"}
_AI_TECHS = {"AI", "ML", "Data Engineering"}


def _to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _city_of(location: Optional[str], explicit_city: Optional[str]) -> Optional[str]:
    if explicit_city:
        return explicit_city.strip()
    if location:
        return location.split(",")[0].strip() or None
    return None


@dataclass
class JobInput:
    """A single normalized job posting fed to the aggregator."""

    source_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    location: Optional[str] = None
    city: Optional[str] = None
    industry: Optional[str] = None
    technologies: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)
    contract_type: Optional[str] = None
    external_id: Optional[str] = None
    source_url: Optional[str] = None
    published_at: Optional[datetime] = None
    is_synthetic: bool = False

    @classmethod
    def from_raw_record(cls, rec) -> "JobInput":
        text = " ".join(p for p in (rec.title, rec.description) if p)
        payload = rec.raw_payload or {}
        return cls(
            source_id=rec.source_id,
            title=rec.title,
            description=rec.description,
            company_name=rec.company_name,
            company_domain=rec.company_domain,
            location=rec.location,
            city=payload.get("city"),
            industry=rec.industry,
            technologies=list(rec.technologies) if rec.technologies else extract_technologies(text),
            roles=list(rec.roles) if rec.roles else extract_roles(text),
            contract_type=rec.contract_type,
            external_id=rec.external_id,
            source_url=rec.source_url,
            published_at=_to_naive_utc(rec.published_at),
            is_synthetic=bool(rec.is_synthetic),
        )


@dataclass
class CompanyAggregate:
    normalized_name: str
    display_name: str
    company_domain: Optional[str] = None
    provenance: DataProvenance = DataProvenance.REAL
    jobs: list[JobInput] = field(default_factory=list)
    it_job_count: int = 0
    recent_counts: dict[int, int] = field(default_factory=dict)  # window_days -> count
    recent_job_count: int = 0
    technologies: Counter = field(default_factory=Counter)
    roles: Counter = field(default_factory=Counter)
    cities: Counter = field(default_factory=Counter)
    industries: Counter = field(default_factory=Counter)
    sources: set = field(default_factory=set)
    senior_count: int = 0
    last_signal_date: Optional[datetime] = None
    hiring_intensity: HiringIntensity = HiringIntensity.LOW
    company_type: CompanyType = CompanyType.OTHER_TECHNOLOGY
    company_signals: list[str] = field(default_factory=list)
    primary_signal: SignalType = SignalType.HIRING
    primary_target_role: Optional[str] = None
    evidence: list[dict] = field(default_factory=list)

    @property
    def recent_ratio(self) -> float:
        return (self.recent_job_count / self.it_job_count) if self.it_job_count else 0.0

    @property
    def top_technologies(self) -> list[str]:
        return [t for t, _ in self.technologies.most_common()]

    @property
    def top_roles(self) -> list[str]:
        return [r for r, _ in self.roles.most_common()]


def _content_key(job: JobInput) -> tuple:
    """Content identity of a posting: company + title + city.

    Used to detect the SAME posting appearing on multiple sources."""
    title = (job.title or "").strip().lower()
    city = (_city_of(job.location, job.city) or "").lower()
    return (normalize_company_name(job.company_name), title, city)


def _unit_key(job: JobInput) -> tuple:
    """A single posting within one source (source + external id/title)."""
    return (_content_key(job), job.source_id, (job.external_id or "").strip() or (job.title or "").strip().lower())


def _is_senior(title: Optional[str]) -> bool:
    t = (title or "").lower()
    return any(tok in t for tok in _SENIORITY_TOKENS)


def compute_hiring_intensity(it_job_count: int, config: AggregationConfig) -> HiringIntensity:
    if it_job_count >= config.intensity_very_high:
        return HiringIntensity.VERY_HIGH
    if it_job_count >= config.intensity_high:
        return HiringIntensity.HIGH
    if it_job_count >= config.intensity_medium:
        return HiringIntensity.MEDIUM
    return HiringIntensity.LOW


def _classify_company_type(agg: CompanyAggregate) -> CompanyType:
    """Evidence-based classification from industry text + technology mix."""
    industry_text = " ".join(agg.industries).lower()
    techs = set(agg.technologies)
    text = industry_text
    if any(k in text for k in ("fintech", "banking", "financial")):
        return CompanyType.FINTECH_TECH
    if any(k in text for k in ("health", "medical")):
        return CompanyType.HEALTHTECH
    if any(k in text for k in ("security", "cyber", "infosec")):
        return CompanyType.CYBERSECURITY
    if any(k in text for k in ("e-commerce", "ecommerce", "commerce")):
        return CompanyType.ECOMMERCE_TECH
    if any(k in text for k in ("consulting", "services")):
        return CompanyType.IT_SERVICES if "services" in text else CompanyType.IT_CONSULTING
    if any(k in text for k in ("saas", "software as a service")):
        return CompanyType.SAAS
    if "cloud" in text or (techs & {"AWS", "Azure", "GCP"} and "Kubernetes" in techs):
        return CompanyType.CLOUD
    if techs & _AI_TECHS and len(techs & _AI_TECHS) >= 1 and "AI" in techs | {""}:
        return CompanyType.AI_ML
    if "software" in text or "product" in text:
        return CompanyType.SOFTWARE_PRODUCT
    if any(k in text for k in ("enterprise", "erp", "crm")):
        return CompanyType.ENTERPRISE_SOFTWARE
    return CompanyType.OTHER_TECHNOLOGY


def _detect_signals(agg: CompanyAggregate, config: AggregationConfig) -> list[str]:
    signals: list[str] = []
    if agg.it_job_count >= config.large_hiring_min:
        signals.append("LARGE_TECH_HIRING")
    if agg.recent_ratio >= config.rapid_hiring_recent_ratio and agg.recent_job_count >= config.rapid_hiring_min_recent:
        signals.append("RAPID_HIRING")
    distinct_tech = len(agg.technologies)
    if distinct_tech >= config.multi_tech_min:
        signals.append("MULTI_TECH_HIRING")
    if len(agg.cities) >= config.multi_city_min:
        signals.append("ENGINEERING_EXPANSION")
    # Evidence-based content signals.
    blob = " ".join(
        " ".join(p for p in (j.title, j.description, j.contract_type) if p).lower() for j in agg.jobs
    )
    if any(tok in blob for tok in _VENDOR_TOKENS):
        signals.append("VENDOR_REQUIREMENT")
    cloud_share = sum(agg.technologies[t] for t in _CLOUD_TECHS)
    if cloud_share and distinct_tech and cloud_share >= max(3, agg.it_job_count * 0.4):
        signals.append("CLOUD_MIGRATION")
    if sum(agg.technologies[t] for t in _AI_TECHS) >= max(2, agg.it_job_count * 0.3):
        signals.append("AI_INITIATIVE")
    if "digital transformation" in blob or "modernization" in blob or "modernisation" in blob:
        signals.append("DIGITAL_TRANSFORMATION")
    return signals


# Map company signals onto the existing SignalType (highest priority first) so
# the dashboard's signal chart keeps working.
_SIGNAL_PRIORITY: tuple[tuple[str, SignalType], ...] = (
    ("LARGE_TECH_HIRING", SignalType.HIRING),
    ("VENDOR_REQUIREMENT", SignalType.VENDOR_REQUIREMENT),
    ("DIGITAL_TRANSFORMATION", SignalType.DIGITAL_TRANSFORMATION),
    ("CLOUD_MIGRATION", SignalType.DIGITAL_TRANSFORMATION),
    ("AI_INITIATIVE", SignalType.TECHNOLOGY_INITIATIVE),
    ("ENGINEERING_EXPANSION", SignalType.EXPANSION),
    ("RAPID_HIRING", SignalType.HIRING),
    ("MULTI_TECH_HIRING", SignalType.HIRING),
)


def _primary_signal(signals: list[str]) -> SignalType:
    for key, stype in _SIGNAL_PRIORITY:
        if key in signals:
            return stype
    return SignalType.HIRING


def _target_role(intensity: HiringIntensity) -> str:
    if intensity in (HiringIntensity.VERY_HIGH, HiringIntensity.HIGH):
        return "VP Engineering / CTO"
    if intensity is HiringIntensity.MEDIUM:
        return "Engineering Manager / Director"
    return "Engineering Manager / Tech Lead"


def aggregate_companies(
    jobs: Iterable[JobInput],
    *,
    config: AggregationConfig = DEFAULT_AGGREGATION_CONFIG,
    now: Optional[datetime] = None,
) -> list[CompanyAggregate]:
    """Group jobs by normalized company and compute company-level intelligence."""
    now = _to_naive_utc(now) or datetime.now(timezone.utc).replace(tzinfo=None)
    by_company: dict[str, CompanyAggregate] = {}
    seen_units: dict[str, set] = {}          # exact postings already processed
    content_source: dict[str, dict] = {}     # content_key -> first source that counted it

    for job in jobs:
        if not job.company_name:
            continue
        norm = normalize_company_name(job.company_name)
        if not norm:
            continue
        agg = by_company.get(norm)
        if agg is None:
            agg = CompanyAggregate(
                normalized_name=norm,
                display_name=job.company_name.strip(),
                provenance=DataProvenance.SYNTHETIC if job.is_synthetic else DataProvenance.REAL,
            )
            by_company[norm] = agg
            seen_units[norm] = set()
            content_source[norm] = {}

        agg.sources.add(job.source_id)

        # Same exact posting re-seen (same source + id) → ignore, record evidence.
        unit = _unit_key(job)
        if unit in seen_units[norm]:
            _add_evidence(agg, job, duplicate=True)
            continue
        seen_units[norm].add(unit)

        # Same posting from a DIFFERENT source → cross-source confirmation, not a
        # new opening. Distinct requisitions within one source still count.
        ckey = _content_key(job)
        first_source = content_source[norm].get(ckey)
        if first_source is not None and first_source != job.source_id:
            _add_evidence(agg, job, duplicate=True)
            continue
        content_source[norm].setdefault(ckey, job.source_id)

        agg.jobs.append(job)
        agg.it_job_count += 1
        if job.company_domain and not agg.company_domain:
            agg.company_domain = job.company_domain
        if job.is_synthetic:
            agg.provenance = DataProvenance.SYNTHETIC
        for tech in job.technologies:
            agg.technologies[tech] += 1
        for role in job.roles:
            agg.roles[role] += 1
        city = _city_of(job.location, job.city)
        if city:
            agg.cities[city] += 1
        if job.industry:
            agg.industries[job.industry] += 1
        if _is_senior(job.title):
            agg.senior_count += 1
        pub = _to_naive_utc(job.published_at)
        if pub:
            if agg.last_signal_date is None or pub > agg.last_signal_date:
                agg.last_signal_date = pub
            for window in config.fresh_windows:
                if pub >= now - timedelta(days=window):
                    agg.recent_counts[window] = agg.recent_counts.get(window, 0) + 1
        _add_evidence(agg, job, duplicate=False)

    # Finalize derived fields.
    results: list[CompanyAggregate] = []
    for agg in by_company.values():
        if agg.it_job_count < config.min_jobs_for_lead:
            continue
        agg.recent_job_count = agg.recent_counts.get(config.recent_days, 0)
        agg.hiring_intensity = compute_hiring_intensity(agg.it_job_count, config)
        agg.company_type = _classify_company_type(agg)
        agg.company_signals = _detect_signals(agg, config)
        agg.primary_signal = _primary_signal(agg.company_signals)
        agg.primary_target_role = _target_role(agg.hiring_intensity)
        results.append(agg)

    results.sort(key=lambda a: (a.it_job_count, a.recent_job_count), reverse=True)
    return results


def _add_evidence(agg: CompanyAggregate, job: JobInput, *, duplicate: bool) -> None:
    pub = _to_naive_utc(job.published_at)
    agg.evidence.append({
        "source": job.source_id,
        "source_id": job.source_id,
        "source_url": job.source_url,
        "job_title": job.title,
        "published_at": pub.isoformat() if pub else None,
        "external_id": job.external_id,
        "duplicate_of_prior_source": duplicate,
    })


def technology_demand(jobs: Iterable[JobInput]) -> list[dict]:
    """Aggregate technology demand across all companies: openings + company count."""
    openings: Counter = Counter()
    companies: dict[str, set] = {}
    for job in jobs:
        norm = normalize_company_name(job.company_name) if job.company_name else ""
        for tech in set(job.technologies):
            openings[tech] += 1
            companies.setdefault(tech, set()).add(norm)
    demand = [
        {"technology": tech, "openings": openings[tech], "companies": len(companies.get(tech, set()))}
        for tech in openings
    ]
    demand.sort(key=lambda d: (d["openings"], d["companies"]), reverse=True)
    return demand
