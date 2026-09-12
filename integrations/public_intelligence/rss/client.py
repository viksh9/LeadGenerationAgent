"""Minimal RSS/Atom parser for configured public feeds (stdlib only).

Parses feed XML into normalized entries (title/link/published). No network here —
the raw feed text is supplied by the provider so this is fully unit-testable.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional


@dataclass
class RssEntry:
    title: Optional[str]
    link: Optional[str]
    published: Optional[str]
    source_url: Optional[str] = None


def _text(el: Optional[ET.Element]) -> Optional[str]:
    return el.text.strip() if (el is not None and el.text) else None


class RssClient:
    """Parse RSS 2.0 <item> and Atom <entry> elements. Namespace-tolerant."""

    def parse(self, xml_text: str, *, source_url: Optional[str] = None) -> list[RssEntry]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []
        entries: list[RssEntry] = []
        for el in root.iter():
            tag = el.tag.rsplit("}", 1)[-1].lower()
            if tag not in ("item", "entry"):
                continue
            title = link = published = None
            for child in el:
                ctag = child.tag.rsplit("}", 1)[-1].lower()
                if ctag == "title":
                    title = _text(child)
                elif ctag == "link":
                    link = child.get("href") or _text(child)
                elif ctag in ("pubdate", "published", "updated"):
                    published = published or _text(child)
            entries.append(RssEntry(title=title, link=link, published=published, source_url=source_url))
        return entries
