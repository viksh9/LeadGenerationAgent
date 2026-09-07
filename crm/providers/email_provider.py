"""Email provider abstraction (§9, §10, §11).

``BaseEmailProvider`` defines the contract; ``SMTPEmailProvider`` is a real
implementation over stdlib ``smtplib``. Additional providers (SendGrid, Microsoft
Graph, Gmail API, ...) can be added later behind the same interface.

Safety: ``build_email_provider`` returns ``None`` unless a provider is actually
configured, so the send flow physically cannot send without configuration. A send
is reported successful ONLY when the transport confirms it — on any failure the
result is ``success=False`` and the caller must NOT mark the message SENT (§11).
Credentials come from settings/env only and are never logged.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid

from config.settings import Settings, get_settings
from database.models import EmailProviderStatus

logger = logging.getLogger(__name__)


@dataclass
class EmailSendResult:
    success: bool
    provider: str
    provider_message_id: str | None = None
    error: str | None = None


class BaseEmailProvider(ABC):
    name: str = "BASE"

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def send(self, *, to: str, subject: str, body: str, from_addr: str) -> EmailSendResult: ...

    def probe(self) -> EmailProviderStatus:
        """Best-effort connectivity check. Default reports config state only —
        CONNECTED is only returned by a provider that made a real connection."""
        return EmailProviderStatus.CONFIGURED if self.is_configured() else EmailProviderStatus.NOT_CONFIGURED


class SMTPEmailProvider(BaseEmailProvider):
    name = "SMTP"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def is_configured(self) -> bool:
        s = self.settings
        return bool(s.smtp_host and s.email_from)

    def send(self, *, to: str, subject: str, body: str, from_addr: str) -> EmailSendResult:
        if not self.is_configured():
            return EmailSendResult(False, self.name, error="SMTP not configured")
        s = self.settings
        msg = EmailMessage()
        msg["From"] = from_addr
        msg["To"] = to
        msg["Subject"] = subject
        message_id = make_msgid()
        msg["Message-ID"] = message_id
        msg.set_content(body)
        try:
            if s.smtp_use_tls:
                context = ssl.create_default_context()
                with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as server:
                    server.starttls(context=context)
                    if s.smtp_username and s.smtp_password:
                        server.login(s.smtp_username, s.smtp_password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as server:
                    if s.smtp_username and s.smtp_password:
                        server.login(s.smtp_username, s.smtp_password)
                    server.send_message(msg)
            return EmailSendResult(True, self.name, provider_message_id=message_id)
        except Exception as exc:  # noqa: BLE001 — any transport error means NOT sent
            # Sanitized error; never include credentials.
            return EmailSendResult(False, self.name, error=f"{type(exc).__name__}: {exc}"[:400])

    def probe(self) -> EmailProviderStatus:
        if not self.is_configured():
            return EmailProviderStatus.NOT_CONFIGURED
        s = self.settings
        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as server:
                server.noop()
            return EmailProviderStatus.CONNECTED
        except Exception:  # noqa: BLE001
            return EmailProviderStatus.ERROR


def build_email_provider(settings: Settings | None = None) -> BaseEmailProvider | None:
    """Return a configured provider, or None when no provider is configured."""
    settings = settings or get_settings()
    provider = (settings.email_provider or "").strip().upper()
    if not provider:
        return None
    if provider == "SMTP":
        p = SMTPEmailProvider(settings)
        return p if p.is_configured() else None
    # Other providers (SENDGRID/GRAPH/GMAIL) are recognised names but not yet
    # implemented — report NOT_CONFIGURED rather than pretend to send.
    logger.info("email provider '%s' is not implemented yet; treating as NOT_CONFIGURED", provider)
    return None


def email_provider_status(settings: Settings | None = None) -> EmailProviderStatus:
    settings = settings or get_settings()
    if (settings.email_provider or "").strip() == "":
        return EmailProviderStatus.NOT_CONFIGURED
    provider = build_email_provider(settings)
    if provider is None:
        return EmailProviderStatus.NOT_CONFIGURED
    return EmailProviderStatus.CONFIGURED
