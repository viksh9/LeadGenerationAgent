"""OpenCorporates legal-entity verification provider (Prompt 47)."""

from integrations.public_intelligence.opencorporates.client import OpenCorporatesClient
from integrations.public_intelligence.opencorporates.provider import OpenCorporatesProvider

__all__ = ["OpenCorporatesClient", "OpenCorporatesProvider"]
