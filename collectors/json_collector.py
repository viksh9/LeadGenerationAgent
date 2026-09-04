"""Load company and signal records from a JSON file (offline / sample source)."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from collectors.base import Collector, RawCompanyRecord, RawSignal
from config import get_settings
from config.exceptions import CollectorError

logger = logging.getLogger(__name__)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class JsonFileCollector(Collector):
    """Phase 1 collector: local JSON only. No network or scraping."""

    name = "json_file"

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or get_settings().default_sample_path)

    def collect(self) -> list[RawCompanyRecord]:
        if not self.path.is_file():
            raise CollectorError(f"Sample lead file not found: {self.path}")
        try:
            payload: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CollectorError(f"Sample lead file is not valid JSON: {self.path}") from exc
        logger.info("json_collector_loaded path=%s", self.path)
        records: list[RawCompanyRecord] = []
        for company in payload.get("companies", []):
            signals = [
                RawSignal(
                    signal_type=item["signal_type"],
                    title=item["title"],
                    description=item.get("description"),
                    source=item.get("source"),
                    source_url=item.get("source_url"),
                    strength=float(item.get("strength", 0.5)),
                    observed_at=_parse_datetime(item.get("observed_at")),
                    extra=item.get("extra") or {},
                )
                for item in company.get("signals", [])
            ]
            records.append(
                RawCompanyRecord(
                    name=company["name"],
                    domain=company.get("domain"),
                    industry=company.get("industry"),
                    size=company.get("size"),
                    location=company.get("location"),
                    description=company.get("description"),
                    signals=signals,
                    contacts=list(company.get("contacts") or []),
                )
            )
        return records
