"""Normalization orchestrator: raw record -> NormalizedJobRecord.

Pure/deterministic (no network, no LLM, no DB). Preserves every original source
field and produces normalized fields separately, with per-record warnings and a
normalization_confidence. Cross-source dedup / company merging are NOT done here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional

from database.models import DataProvenance
from ingestion.extract import normalize_role as _display_role
from processors.normalization.company_normalizer import normalize_company
from processors.normalization.date_normalizer import normalize_date
from processors.normalization.field_normalizers import (
    EmploymentType,
    normalize_employment_type,
    normalize_experience,
    normalize_salary,
    normalize_source_name,
    normalize_url,
)
from processors.normalization.industry_normalizer import IndustryTaxonomy, normalize_industry
from processors.normalization.location_normalizer import normalize_location
from processors.normalization.relevance import is_it_relevant_job
from processors.normalization.result import NormalizedJobRecord
from processors.normalization.role_normalizer import RoleTaxonomy, normalize_role_taxonomy
from processors.normalization.technology_normalizer import normalize_technologies
from processors.normalization.title_normalizer import extract_seniority, normalize_title

logger = logging.getLogger("normalization")

NORMALIZATION_VERSION = "1.0.0"


def _get(rec: Any, key: str, default: Any = None) -> Any:
    if isinstance(rec, dict):
        return rec.get(key, default)
    return getattr(rec, key, default)


@dataclass
class BatchSummary:
    total: int = 0
    normalized: int = 0
    warnings: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


class JobNormalizer:
    version = NORMALIZATION_VERSION

    def normalize_job(self, raw: Any, *, now: Optional[datetime] = None) -> NormalizedJobRecord:
        title = _get(raw, "title")
        description = _get(raw, "description")
        text = " ".join(p for p in (title, description) if p)
        source_terms = list(_get(raw, "technologies", []) or [])
        warnings: list[str] = []

        norm_title, tw = normalize_title(title)
        warnings.extend(tw)
        seniority = extract_seniority(title)
        role_taxonomy = normalize_role_taxonomy(title, description)
        technologies, categories = normalize_technologies(text=text, terms=source_terms)

        loc = normalize_location(_get(raw, "location"))
        warnings.extend(loc.warnings)

        company = normalize_company(
            _get(raw, "company_name"),
            domain_or_url=_get(raw, "company_domain") or _get(raw, "company_website"),
            source_company_id=_get(raw, "source_company_id"),
        )
        warnings.extend(company.warnings)

        industry = normalize_industry(_get(raw, "industry"))
        employment = normalize_employment_type(_get(raw, "contract_type") or _get(raw, "employment_type"))
        exp_min, exp_max = normalize_experience(description)
        salary_text = _get(raw, "salary")
        s_min, s_max, currency, period, sw = normalize_salary(salary_text)
        warnings.extend(sw)

        pub_raw = _get(raw, "published_at")
        published_at, dw = normalize_date(pub_raw, now=now)
        warnings.extend(dw)
        updated_at, _ = normalize_date(_get(raw, "updated_at"), now=now)

        source = normalize_source_name(_get(raw, "source_id") or _get(raw, "source_name"))
        norm_url, uw = normalize_url(_get(raw, "source_url"))
        warnings.extend(uw)

        relevance = is_it_relevant_job(
            title=title, description=description, technologies=technologies,
            role_taxonomy=role_taxonomy, industry=industry,
        )

        provenance = DataProvenance.SYNTHETIC if _get(raw, "is_synthetic") else DataProvenance.REAL

        record = NormalizedJobRecord(
            original_job_title=title,
            original_company_name=_get(raw, "company_name"),
            original_location=_get(raw, "location"),
            original_description=description,
            original_source_url=_get(raw, "source_url"),
            original_technology_terms=source_terms,
            original_salary_text=salary_text,
            original_date_text=str(pub_raw) if pub_raw is not None else None,
            original_source=_get(raw, "source_id") or _get(raw, "source_name"),
            normalized_job_title=norm_title,
            normalized_role=_display_role(title),
            role_taxonomy=role_taxonomy,
            seniority_level=seniority,
            normalized_technologies=technologies,
            technology_categories=categories,
            normalized_city=loc.normalized_city,
            normalized_state=loc.normalized_state,
            normalized_country=loc.normalized_country,
            normalized_region=loc.normalized_region,
            remote_type=loc.remote_type,
            normalized_company_name=company.normalized_company_name,
            company_domain=company.company_domain,
            company_identity_confidence=company.company_identity_confidence,
            industry=industry,
            it_relevance=relevance,
            employment_type=employment,
            experience_min=exp_min,
            experience_max=exp_max,
            salary_min=s_min,
            salary_max=s_max,
            currency=currency,
            salary_period=period,
            published_at=published_at,
            updated_at=updated_at,
            normalized_source=source,
            normalized_source_url=norm_url,
            data_provenance=provenance,
            normalization_warnings=warnings,
            normalization_version=self.version,
        )
        record.normalization_confidence = _confidence(record)
        return record

    def normalize_many(self, records: Iterable[Any], *, now: Optional[datetime] = None) -> tuple[list[NormalizedJobRecord], BatchSummary]:
        out: list[NormalizedJobRecord] = []
        summary = BatchSummary()
        for rec in records:
            summary.total += 1
            try:
                normalized = self.normalize_job(rec, now=now)
            except Exception as exc:  # noqa: BLE001 - one bad record must not fail the batch
                summary.failed += 1
                summary.errors.append(str(exc))
                logger.warning("normalize_failed error=%s", exc)
                continue
            out.append(normalized)
            summary.normalized += 1
            if normalized.normalization_warnings:
                summary.warnings += 1
        return out, summary


def _confidence(r: NormalizedJobRecord) -> int:
    score = 0
    score += 20 if r.company_identity_confidence > 0 else 0
    score += 15 if r.normalized_job_title else 0
    score += 15 if r.normalized_city else 0
    score += 15 if r.normalized_technologies else 0
    score += 10 if r.published_at else 0
    score += 10 if r.role_taxonomy not in (RoleTaxonomy.OTHER, RoleTaxonomy.UNKNOWN) else 0
    score += 10 if r.it_relevance.value != "UNKNOWN" else 0
    score += 5 if r.normalized_source.value != "OTHER" else 0
    return min(100, score)


# Module-level convenience wrappers.
_DEFAULT = JobNormalizer()


def normalize_job(raw: Any, *, now: Optional[datetime] = None) -> NormalizedJobRecord:
    return _DEFAULT.normalize_job(raw, now=now)


def normalize_many(records: Iterable[Any], *, now: Optional[datetime] = None) -> tuple[list[NormalizedJobRecord], BatchSummary]:
    return _DEFAULT.normalize_many(records, now=now)
