"""CRM provider abstraction (§18, §19, §20).

``BaseCRMProvider`` is the extension point for external CRMs (Salesforce, HubSpot,
Zoho, Pipedrive). Only ``InternalCRMProvider`` is implemented — the local database
IS the CRM (source of truth for internal lead/sales state, §63). External
connectors are not implemented unless credentials/docs are available; attempting
to build one reports NOT_CONFIGURED rather than pretending to connect.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from config.settings import Settings, get_settings
from database.models import CRMSyncStatus


@dataclass
class CRMSyncOutcome:
    ok: bool
    external_id: str | None = None
    error: str | None = None


class BaseCRMProvider(ABC):
    name: str = "BASE"

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def connect(self) -> bool:
        """Return True only if a real connection to the provider succeeded."""

    @abstractmethod
    def upsert(self, entity_type: str, local_id: int, payload: dict) -> CRMSyncOutcome: ...

    def status(self) -> CRMSyncStatus:
        return CRMSyncStatus.CONFIGURED if self.is_configured() else CRMSyncStatus.NOT_CONFIGURED


class InternalCRMProvider(BaseCRMProvider):
    """The local database is the CRM. No external calls; always available. Sync is
    a no-op that confirms the local record is the source of truth."""

    name = "INTERNAL"

    def is_configured(self) -> bool:
        return True

    def connect(self) -> bool:
        return True

    def upsert(self, entity_type: str, local_id: int, payload: dict) -> CRMSyncOutcome:
        # Internal CRM: the local row already IS the record of truth.
        return CRMSyncOutcome(ok=True, external_id=f"internal:{entity_type}:{local_id}")

    def status(self) -> CRMSyncStatus:
        return CRMSyncStatus.CONNECTED   # local store is always "connected"


def build_crm_provider(settings: Settings | None = None) -> BaseCRMProvider:
    """Return the configured CRM provider. Defaults to the internal CRM. External
    connectors are not implemented; an unknown/external provider name still yields
    the internal provider (never a fake external connection)."""
    settings = settings or get_settings()
    provider = (settings.crm_provider or "INTERNAL").strip().upper()
    if provider == "INTERNAL":
        return InternalCRMProvider()
    # External connectors are intentionally not implemented in this phase.
    return InternalCRMProvider()


def crm_provider_status(settings: Settings | None = None) -> CRMSyncStatus:
    settings = settings or get_settings()
    provider = (settings.crm_provider or "INTERNAL").strip().upper()
    if provider == "INTERNAL":
        return CRMSyncStatus.CONNECTED
    # External configured but not implemented → CONFIGURED (not CONNECTED).
    return CRMSyncStatus.CONFIGURED if settings.crm_api_key else CRMSyncStatus.NOT_CONFIGURED
