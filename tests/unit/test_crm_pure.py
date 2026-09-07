"""Pure-logic unit tests for the CRM/outreach layer (§14, §15, §25, §39, §65).
No DB, no network."""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from api.security import _allow, resolve_role
from crm.analytics import INSUFFICIENT_DATA, _rate
from crm.lifecycle import LeadLifecycleService
from crm.webhooks import verify_signature
from database.models import (
    ContactType,
    DecisionMaker,
    EmailStatus,
    LeadStatus,
    UserRole,
    VerificationStatus,
)
from outreach.ai_reply import classify_reply
from outreach.contacts import has_verified_business_email, is_valid_email
from database.models import ReplyClassification


# --- Reply classification (§15) grounded in the message ------------------- #
@pytest.mark.parametrize("text,expected", [
    ("We are interested, let's schedule a call", ReplyClassification.MEETING_REQUEST),
    ("Please send me more information and pricing", ReplyClassification.REQUEST_MORE_INFO),
    ("I am out of office until Monday", ReplyClassification.OUT_OF_OFFICE),
    ("Not interested, thanks", ReplyClassification.NEGATIVE),
    ("Let's revisit next quarter", ReplyClassification.NOT_NOW),
    ("please remove me / unsubscribe", ReplyClassification.NOT_RELEVANT),
])
def test_reply_classification(text, expected):
    res = classify_reply(text)
    assert res.classification is expected
    assert res.quote        # grounded in the actual text


def test_reply_classification_empty_is_unknown():
    assert classify_reply("").classification is ReplyClassification.UNKNOWN
    assert classify_reply(None).classification is ReplyClassification.UNKNOWN


# --- Verified business email (§10) ---------------------------------------- #
def _dm(**over):
    base = dict(business_email="a@corp.com", email_status=EmailStatus.VERIFIED_SOURCE,
                contact_type=ContactType.BUSINESS_EMAIL, verification_status=VerificationStatus.VERIFIED)
    base.update(over)
    return DecisionMaker(company_name="C", normalized_name="x", **base)


def test_verified_business_email_accepts_real():
    assert has_verified_business_email(_dm()) is True


def test_verified_email_rejects_unverified_or_guessed():
    assert not has_verified_business_email(_dm(email_status=EmailStatus.UNVERIFIED_SOURCE))
    assert not has_verified_business_email(_dm(contact_type=ContactType.PROFESSIONAL_PROFILE))
    assert not has_verified_business_email(_dm(verification_status=VerificationStatus.UNVERIFIED))
    assert not has_verified_business_email(_dm(business_email=None))


def test_is_valid_email():
    assert is_valid_email("a@b.co")
    assert not is_valid_email("nope")
    assert not is_valid_email(None)


# --- Analytics honesty (§25) ---------------------------------------------- #
def test_rate_insufficient_data_on_zero_denominator():
    assert _rate(0, 0) == INSUFFICIENT_DATA
    assert _rate(3, 5) == 0.6


# --- Webhook signature (§39, §65) ----------------------------------------- #
def _sign(secret, payload, ts):
    return hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()


def test_webhook_signature_valid():
    secret, payload, ts = "s", b'{"a":1}', str(int(time.time()))
    sig = _sign(secret, payload, ts)
    assert verify_signature(secret, payload=payload, signature_header=sig, timestamp_header=ts,
                            tolerance_seconds=300, now_ts=time.time())


def test_webhook_signature_rejects_tamper_stale_and_missing_secret():
    secret, payload, ts = "s", b'{"a":1}', str(int(time.time()))
    sig = _sign(secret, payload, ts)
    # tampered payload
    assert not verify_signature(secret, payload=b'{"a":2}', signature_header=sig, timestamp_header=ts,
                                tolerance_seconds=300, now_ts=time.time())
    # stale timestamp
    assert not verify_signature(secret, payload=payload, signature_header=sig, timestamp_header="1000",
                                tolerance_seconds=300, now_ts=time.time())
    # no secret → fail closed
    assert not verify_signature(None, payload=payload, signature_header=sig, timestamp_header=ts,
                                tolerance_seconds=300, now_ts=time.time())


# --- RBAC resolution (§42) ------------------------------------------------ #
def test_rbac_open_when_no_admin_key(monkeypatch):
    from config import settings as sm
    monkeypatch.setattr(sm.get_settings(), "admin_api_key", None)
    assert resolve_role(None, None) is UserRole.ADMIN   # local single-user stays open


def test_rbac_enforced_when_admin_key_set(monkeypatch):
    from config import settings as sm
    monkeypatch.setattr(sm.get_settings(), "admin_api_key", "k")
    assert resolve_role("k", None) is UserRole.ADMIN
    assert resolve_role(None, "SALES") is UserRole.SALES
    assert resolve_role(None, None) is UserRole.VIEWER
    assert resolve_role("wrong", "bogus-role") is UserRole.VIEWER


# --- Rate limiter (§43) --------------------------------------------------- #
def test_rate_limiter_allows_then_blocks():
    key = "unit-test-key"
    assert _allow(key, 2, ts=1000.0)
    assert _allow(key, 2, ts=1000.1)
    assert not _allow(key, 2, ts=1000.2)     # third within the window is blocked
    assert _allow(key, 2, ts=1100.0)          # window rolled over
