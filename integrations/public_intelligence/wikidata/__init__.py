"""Wikidata public SPARQL provider (company identity verification)."""

from integrations.public_intelligence.wikidata.client import WikidataClient
from integrations.public_intelligence.wikidata.provider import WikidataProvider

__all__ = ["WikidataClient", "WikidataProvider"]
