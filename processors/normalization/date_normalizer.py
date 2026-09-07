"""Date normalization: many source formats -> naive UTC datetime.

Relative dates ("2 days ago", "yesterday") are resolved ONLY against a known
reference time (collection time). Ambiguous numeric formats are flagged. Never
fabricates a date.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?")
_DMY = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")
_REL_DAYS = re.compile(r"(\d+)\s*day", re.IGNORECASE)
_REL_HOURS = re.compile(r"(\d+)\s*hour", re.IGNORECASE)


def _to_naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def normalize_date(text, *, now: Optional[datetime] = None) -> tuple[Optional[datetime], list[str]]:
    """Return (naive-UTC datetime, warnings). `now` is required to resolve
    relative dates; without it relative text yields a warning, not a guess."""
    warnings: list[str] = []
    if text is None:
        return (None, warnings)
    if isinstance(text, datetime):
        return (_to_naive(text), warnings)
    value = str(text).strip()
    if not value:
        return (None, warnings)
    low = value.lower()

    # Relative dates.
    if "today" in low or "just now" in low:
        return (now, warnings) if now else (None, ["relative date without reference time"])
    if "yesterday" in low:
        return (now - timedelta(days=1), warnings) if now else (None, ["relative date without reference time"])
    m = _REL_DAYS.search(low)
    if m and "ago" in low:
        return (now - timedelta(days=int(m.group(1))), warnings) if now else (None, ["relative date without reference time"])
    m = _REL_HOURS.search(low)
    if m and "ago" in low:
        return (now - timedelta(hours=int(m.group(1))), warnings) if now else (None, ["relative date without reference time"])

    # ISO.
    if _ISO.match(value):
        try:
            return (_to_naive(datetime.fromisoformat(value.replace("Z", "+00:00"))), warnings)
        except ValueError:
            pass

    # RFC822 (RSS).
    try:
        dt = parsedate_to_datetime(value)
        if dt is not None:
            return (_to_naive(dt), warnings)
    except (TypeError, ValueError, IndexError):
        pass

    # DD/MM/YYYY or MM/DD/YYYY.
    m = _DMY.match(value)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a > 12 and b <= 12:          # unambiguous -> DD/MM
            return (datetime(y, b, a), warnings)
        if b > 12 and a <= 12:          # unambiguous -> MM/DD
            return (datetime(y, a, b), warnings)
        # Ambiguous: prefer DD/MM (India) but flag it.
        warnings.append("Date format ambiguous (assumed DD/MM/YYYY)")
        try:
            return (datetime(y, b, a), warnings)
        except ValueError:
            return (None, ["date cannot be parsed"])

    return (None, ["Date could not be parsed"])
