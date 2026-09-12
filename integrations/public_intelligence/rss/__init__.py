"""RSS/Atom public-announcement collector abstraction (configured feeds only).

Parses ONLY the feeds listed in RSS_INTELLIGENCE_FEEDS — never crawls arbitrary news
sites, never fabricates a feed (§16). Announcements are company-level signals (tech
initiatives, expansion, partnerships), not POCs, so this provider contributes no
people to POC discovery; it exists as a real, tested collector abstraction.
"""

from integrations.public_intelligence.rss.client import RssClient, RssEntry
from integrations.public_intelligence.rss.provider import RssProvider

__all__ = ["RssClient", "RssEntry", "RssProvider"]
