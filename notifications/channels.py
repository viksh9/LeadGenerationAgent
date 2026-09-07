"""Notification channel abstraction (§30).

IN_APP is fully implemented (an ``Alert`` row IS the in-app notification). Email,
Slack, and webhook are interface-only: they raise ``ChannelNotConfigured`` unless
explicitly configured, so nothing is ever sent externally without configuration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from database.models import Alert


class ChannelNotConfigured(RuntimeError):
    """Raised when a channel is used without explicit configuration."""


class NotificationChannel(ABC):
    name: str = "BASE"

    @abstractmethod
    def is_configured(self) -> bool:
        ...

    @abstractmethod
    def deliver(self, alert: Alert) -> bool:
        """Deliver an already-persisted alert. Returns True on success."""


class InAppChannel(NotificationChannel):
    """The alert row itself is the in-app notification; no external delivery."""

    name = "IN_APP"

    def is_configured(self) -> bool:
        return True

    def deliver(self, alert: Alert) -> bool:
        return True   # persisted alert is immediately visible in-app


class _StubExternalChannel(NotificationChannel):
    """Interface placeholder for an external channel. Never sends until wired to
    a real, explicitly-configured integration."""

    def is_configured(self) -> bool:
        return False

    def deliver(self, alert: Alert) -> bool:
        raise ChannelNotConfigured(
            f"{self.name} channel is not configured; no external notification sent."
        )


class EmailChannel(_StubExternalChannel):
    name = "EMAIL"


class SlackChannel(_StubExternalChannel):
    name = "SLACK"


class WebhookChannel(_StubExternalChannel):
    name = "WEBHOOK"


def available_channels() -> dict[str, NotificationChannel]:
    """Registry of channels. Only IN_APP is active by default."""
    return {
        InAppChannel.name: InAppChannel(),
        EmailChannel.name: EmailChannel(),
        SlackChannel.name: SlackChannel(),
        WebhookChannel.name: WebhookChannel(),
    }
