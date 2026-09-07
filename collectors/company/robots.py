"""robots.txt policy check (§20).

Reusable, testable policy: fetches a host's robots.txt via an injected text
fetcher (so unit tests never hit the network) and answers ALLOWED / DISALLOWED /
UNKNOWN for a given URL + user agent. Restrictions are never bypassed; when the
policy is unclear the result is UNKNOWN and the caller decides conservatively.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from collectors.company.sources import RobotsStatus

logger = logging.getLogger("collectors")

# Callable that returns robots.txt text for a robots URL, or None if unavailable.
TextFetcher = Callable[[str], Optional[str]]


class RobotsPolicy:
    def __init__(self, fetch_text: TextFetcher, *, user_agent: str) -> None:
        self._fetch_text = fetch_text
        self._user_agent = user_agent
        self._cache: dict[str, Optional[RobotFileParser]] = {}

    def _robots_for(self, url: str) -> Optional[RobotFileParser]:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._cache:
            return self._cache[origin]
        text = self._fetch_text(f"{origin}/robots.txt")
        parser: Optional[RobotFileParser]
        if text is None:
            parser = None  # unavailable → UNKNOWN
        else:
            parser = RobotFileParser()
            parser.parse(text.splitlines())
        self._cache[origin] = parser
        return parser

    def check(self, url: str, *, source_id: str | None = None) -> RobotsStatus:
        """Return the robots posture for `url` under our user agent."""
        parser = self._robots_for(url)
        if parser is None:
            status = RobotsStatus.UNKNOWN
        else:
            allowed = parser.can_fetch(self._user_agent, url)
            status = RobotsStatus.ALLOWED if allowed else RobotsStatus.DISALLOWED
        logger.info(
            "robots_check source_id=%s host=%s robots_status=%s",
            source_id, urlsplit(url).hostname, status.value,
        )
        return status
