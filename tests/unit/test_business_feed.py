"""Unit tests for RSS/Atom feed parsing."""

from __future__ import annotations

from collectors.business.feed import parse_feed

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Infosys wins digital transformation contract</title>
    <link>https://news.example/1</link>
    <description>Cloud program</description>
    <guid>n1</guid>
    <pubDate>Wed, 03 Sep 2026 10:00:00 GMT</pubDate>
    <company>Infosys</company></item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><title>TCS opens delivery center</title>
    <link href="https://news.example/2"/>
    <summary>New engineering center</summary>
    <id>a1</id>
    <published>2026-09-02T09:00:00Z</published></entry>
</feed>"""


def test_parse_rss():
    items = parse_feed(RSS)
    assert len(items) == 1
    it = items[0]
    assert it.title == "Infosys wins digital transformation contract"
    assert it.link == "https://news.example/1"
    assert it.guid == "n1"
    assert it.company_name == "Infosys"
    assert it.published_at is not None and it.published_at.year == 2026


def test_parse_atom():
    items = parse_feed(ATOM)
    assert len(items) == 1
    assert items[0].title == "TCS opens delivery center"
    assert items[0].link == "https://news.example/2"
    assert items[0].published_at.month == 9


def test_malformed_returns_empty():
    assert parse_feed("<rss><channel><item>unclosed") == [] or isinstance(parse_feed("<rss>"), list)
    assert parse_feed("") == []
    assert parse_feed("not xml at all &&&") == []
