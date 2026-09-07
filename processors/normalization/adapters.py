"""Source-specific normalization adapters.

The common normalizer handles the standard RawSourceRecord shape. Adapters only
add source-specific field extraction (e.g. Adzuna's structured salary, a career
page's employment type) BEFORE the common normalization runs. Keep the common
layer reusable — add source rules only when necessary.
"""

from __future__ import annotations

from typing import Any

from processors.normalization.normalizer import JobNormalizer
from processors.normalization.result import NormalizedJobRecord


def _base_fields(raw: Any) -> dict:
    keys = (
        "title", "description", "company_name", "company_domain", "company_website",
        "source_company_id", "location", "industry", "technologies", "salary",
        "contract_type", "employment_type", "published_at", "updated_at",
        "source_id", "source_name", "source_url", "is_synthetic",
    )
    return {k: (raw.get(k) if isinstance(raw, dict) else getattr(raw, k, None)) for k in keys}


class CommonAdapter:
    source_id = "common"

    def to_common(self, raw: Any) -> dict:
        return _base_fields(raw)


class AdzunaAdapter(CommonAdapter):
    source_id = "adzuna"

    def to_common(self, raw: Any) -> dict:
        fields = _base_fields(raw)
        payload = (raw.get("raw_payload") if isinstance(raw, dict) else getattr(raw, "raw_payload", None)) or {}
        if not fields.get("salary") and (payload.get("salary_min") or payload.get("salary_max")):
            lo, hi = payload.get("salary_min"), payload.get("salary_max")
            currency = payload.get("salary_currency") or "INR"  # Adzuna India default
            fields["salary"] = f"{currency} {lo or ''}-{hi or ''}".strip().strip("-")
        fields["contract_type"] = fields.get("contract_type") or payload.get("contract_time") or payload.get("contract_type")
        return fields


class CareerPageAdapter(CommonAdapter):
    source_id = "company_career"

    def to_common(self, raw: Any) -> dict:
        fields = _base_fields(raw)
        payload = (raw.get("raw_payload") if isinstance(raw, dict) else getattr(raw, "raw_payload", None)) or {}
        fields["employment_type"] = fields.get("employment_type") or payload.get("employment_type")
        if not fields.get("location") and payload.get("city"):
            fields["location"] = payload["city"]
        return fields


_ADAPTERS: dict[str, CommonAdapter] = {
    "adzuna": AdzunaAdapter(),
    "company_career": CareerPageAdapter(),
    "company_career_pages": CareerPageAdapter(),
    "demo_career": CareerPageAdapter(),
}
_COMMON = CommonAdapter()
_NORMALIZER = JobNormalizer()


def select_adapter(source_id: str | None) -> CommonAdapter:
    return _ADAPTERS.get(source_id or "", _COMMON)


def normalize_raw(raw: Any, *, now=None) -> NormalizedJobRecord:
    """Normalize a raw record using its source-specific adapter."""
    source_id = raw.get("source_id") if isinstance(raw, dict) else getattr(raw, "source_id", None)
    common = select_adapter(source_id).to_common(raw)
    common["raw_payload"] = None  # already extracted; keep normalizer pure
    return _NORMALIZER.normalize_job(common, now=now)
