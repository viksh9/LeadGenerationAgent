"""Minimal RSS/Atom feed parsing (stdlib only — no third-party feed library).

Only structured feed data is parsed; no HTML/JS execution. Handles RSS 2.0
<item> and Atom <entry>, with tolerant date parsing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from xml.etree import ElementTree as ET

logger = logging.getLogger("collectors")

_ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass
class FeedItem:
    title: Optional[str] = None
    link: Optional[str] = None
    summary: Optional[str] = None
    guid: Optional[str] = None
    published_at: Optional[datetime] = None
    company_name: Optional[str] = None  # only if the feed provides it explicitly


def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)  # RFC822 (RSS pubDate)
        if dt is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except (TypeError, ValueError, IndexError):
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))  # ISO (Atom)
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        return None


def _text(el) -> Optional[str]:
    return el.text.strip() if el is not None and el.text else None


def parse_feed(xml_text: str) -> list[FeedItem]:
    """Parse RSS or Atom XML into FeedItems. Returns [] on malformed input."""
    if not xml_text or not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("feed_parse_error error=%s", exc)
        return []

    items: list[FeedItem] = []

    # RSS 2.0
    for item in root.iter("item"):
        link = _text(item.find("link"))
        guid = _text(item.find("guid")) or link
        items.append(FeedItem(
            title=_text(item.find("title")),
            link=link,
            summary=_text(item.find("description")),
            guid=guid,
            published_at=_parse_date(_text(item.find("pubDate")) or _text(item.find("date"))),
            company_name=_text(item.find("company")) or _text(item.find("{*}company")),
        ))

    # Atom
    for entry in root.iter(f"{_ATOM}entry"):
        link_el = entry.find(f"{_ATOM}link")
        link = link_el.get("href") if link_el is not None else None
        items.append(FeedItem(
            title=_text(entry.find(f"{_ATOM}title")),
            link=link,
            summary=_text(entry.find(f"{_ATOM}summary")) or _text(entry.find(f"{_ATOM}content")),
            guid=_text(entry.find(f"{_ATOM}id")) or link,
            published_at=_parse_date(_text(entry.find(f"{_ATOM}published")) or _text(entry.find(f"{_ATOM}updated"))),
        ))

    return items
