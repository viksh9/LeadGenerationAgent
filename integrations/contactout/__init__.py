"""ContactOut integration — real POC / decision-maker discovery and enrichment.

Public surface:
    ContactOutClient / ContactOutConfig / load_contactout_config  (client.py)
    ContactOutPerson / PeopleResult / ContactAvailability          (models.py)
    parse_person / parse_people / parse_enrich                     (mapper.py)
    ContactOut* exceptions                                         (exceptions.py)

Credentials come from configuration only and are never exposed in responses, logs,
the database, Excel, or audit payloads. No data is ever fabricated on failure.
"""

from integrations.contactout.client import (
    ContactOutClient,
    ContactOutConfig,
    load_contactout_config,
)
from integrations.contactout.exceptions import (
    ContactOutAuthError,
    ContactOutBadResponse,
    ContactOutError,
    ContactOutNotConfigured,
    ContactOutRateLimitError,
    ContactOutUnavailableError,
)
from integrations.contactout.mapper import parse_enrich, parse_people, parse_person
from integrations.contactout.models import ContactAvailability, ContactOutPerson, PeopleResult

__all__ = [
    "ContactOutClient",
    "ContactOutConfig",
    "load_contactout_config",
    "ContactOutPerson",
    "PeopleResult",
    "ContactAvailability",
    "parse_person",
    "parse_people",
    "parse_enrich",
    "ContactOutError",
    "ContactOutNotConfigured",
    "ContactOutAuthError",
    "ContactOutRateLimitError",
    "ContactOutUnavailableError",
    "ContactOutBadResponse",
]
