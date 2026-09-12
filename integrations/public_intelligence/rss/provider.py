"""RSS provider — configured feeds only; contributes no POC people (§16)."""

from __future__ import annotations

from config import get_settings
from integrations.public_intelligence.base import PublicIntelligenceProvider
from integrations.public_intelligence.models import CompanyContext, PublicPerson


class RssProvider(PublicIntelligenceProvider):
    name = "rss"
    source_label = "Public RSS/Atom"
    source_type = "rss_feed"

    def configured_feeds(self) -> list[str]:
        raw = get_settings().rss_intelligence_feeds or ""
        return [f.strip() for f in raw.split(",") if f.strip()]

    def discover_people(self, ctx: CompanyContext, roles: list[str]) -> list[PublicPerson]:
        # Announcements are company-level signals, not POCs — no people produced here.
        return []


__all__ = ["RssProvider"]
