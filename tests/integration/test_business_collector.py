"""Offline tests for the BusinessSignalCollector (mocked feed)."""

from __future__ import annotations

import httpx
import pytest

from collectors.base import FetchRequest, HealthStatus
from collectors.business.collector import BusinessSignalCollector
from collectors.business.config import load_business_config
from collectors.company.http_client import RestrictedError
from collectors.company.robots import RobotsPolicy
from collectors.source_registry import get_registry

FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>Infosys wins digital transformation contract</title>
    <link>https://news.example/1</link><description>Cloud AWS program</description>
    <guid>n1</guid><pubDate>Wed, 03 Sep 2026 10:00:00 GMT</pubDate><company>Infosys</company></item>
  <item><title>Local cricket team wins tournament</title>
    <link>https://news.example/2</link><description>Sports</description>
    <guid>n2</guid><pubDate>Wed, 03 Sep 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""


def _handler(request):
    if request.url.path.endswith("/robots.txt"):
        return httpx.Response(200, headers={"content-type": "text/plain"}, text="User-agent: *\nAllow: /")
    return httpx.Response(200, headers={"content-type": "application/rss+xml"}, text=FEED)


def _collector(handler=_handler, *, robots_txt="User-agent: *\nAllow: /"):
    http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    source = get_registry().get("rss_news").model_copy(update={"base_url": "https://news.example/feed"})
    robots = RobotsPolicy(lambda url: robots_txt, user_agent="test")
    config = load_business_config().model_copy(update={"lookback_days": 36500, "requests_per_minute": 0})
    return BusinessSignalCollector(source, config=config, http=http, robots=robots, sleep=lambda *_: None)


def test_collects_relevant_filters_noise():
    result = _collector().fetch(FetchRequest(limit=10))
    assert result.context["feed_items"] == 2
    assert result.records_count == 1  # cricket filtered
    assert result.context["skipped_irrelevant"] == 1
    draft = result.records[0]
    assert draft.record_type == "NEWS_ARTICLE"
    assert draft.raw_payload["detected_signal_type"] == "DIGITAL_TRANSFORMATION"
    assert draft.company_name == "Infosys"


def test_recency_filter():
    from datetime import datetime
    # since in the future -> everything filtered as old
    result = _collector().fetch(FetchRequest(since=datetime(2099, 1, 1)))
    assert result.records_count == 0
    assert result.context["skipped_old"] >= 1


def test_robots_disallow_refuses():
    collector = _collector(robots_txt="User-agent: *\nDisallow: /")
    with pytest.raises(RestrictedError):
        collector.fetch(FetchRequest())


def test_health_healthy():
    assert _collector().health_check().status == HealthStatus.HEALTHY


def test_health_restricted_by_robots():
    assert _collector(robots_txt="User-agent: *\nDisallow: /").health_check().status == HealthStatus.RESTRICTED
