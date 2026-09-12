"""Wikidata public SPARQL client (query.wikidata.org).

No credentials. A descriptive User-Agent is required by Wikidata etiquette (set from
PUBLIC_INTELLIGENCE_USER_AGENT). Resolves a company entity for identity verification
only (§13) — never treated as authoritative for current employment.
"""

from __future__ import annotations

from typing import Optional

import httpx

from config import get_settings
from integrations.public_intelligence.http import PublicJsonClient

_SPARQL = "https://query.wikidata.org/sparql"


def _escape(label: str) -> str:
    return label.replace("\\", "\\\\").replace('"', '\\"')


def build_company_query(name: str) -> str:
    """Exact-label organization lookup with official website / country / industry."""
    lbl = _escape(name.strip())
    return (
        'SELECT ?item ?itemLabel ?website ?countryLabel ?industryLabel WHERE { '
        f'?item rdfs:label "{lbl}"@en . '
        '?item wdt:P31/wdt:P279* wd:Q43229 . '            # subclass of organization
        'OPTIONAL { ?item wdt:P856 ?website. } '           # official website
        'OPTIONAL { ?item wdt:P17 ?country. } '            # country
        'OPTIONAL { ?item wdt:P452 ?industry. } '          # industry
        'SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } '
        '} LIMIT 1'
    )


class WikidataClient:
    def __init__(self, *, http: httpx.Client | None = None, sleep=None) -> None:
        s = get_settings()
        kwargs = dict(base_url=_SPARQL, user_agent=s.public_intelligence_user_agent,
                      timeout_seconds=s.public_intelligence_timeout_seconds,
                      requests_per_minute=s.wikidata_rate_per_minute, http=http)
        if sleep is not None:
            kwargs["sleep"] = sleep
        self._c = PublicJsonClient(**kwargs)

    def find_company(self, name: str) -> Optional[dict]:
        """Return the first SPARQL binding dict, or None when there is no match."""
        data = self._c.get_json(_SPARQL, params={"query": build_company_query(name), "format": "json"},
                                provider="wikidata")
        if not isinstance(data, dict):
            return None
        bindings = (data.get("results") or {}).get("bindings") or []
        return bindings[0] if bindings else None
