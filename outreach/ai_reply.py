"""Reply classification (§15).

Runs ONLY on a real inbound message. Classification is grounded in the actual
received text — the result always carries the matched quote/snippet from the
message, so it can never be a fabricated response. A deterministic keyword
classifier is the default (no external calls). When an AI provider is configured
it may refine the label, but it is bound to the same message text and falls back
to the deterministic result on any error — it never invents content.
"""

from __future__ import annotations

from dataclasses import dataclass

from database.models import ReplyClassification

# Ordered, most-specific first. Each rule: (classification, keywords).
_RULES: list[tuple[ReplyClassification, tuple[str, ...]]] = [
    (ReplyClassification.OUT_OF_OFFICE, ("out of office", "on leave", "annual leave", "vacation",
                                         "away from my desk", "auto-reply", "automatic reply")),
    (ReplyClassification.MEETING_REQUEST, ("schedule a call", "set up a meeting", "book a call",
                                           "calendly", "let's meet", "available to meet", "hop on a call")),
    (ReplyClassification.REQUEST_MORE_INFO, ("more information", "more details", "send me", "tell me more",
                                             "case study", "pricing", "rate card", "profiles")),
    # NEGATIVE / NOT_* are checked BEFORE INTERESTED so "not interested" is not
    # mis-read as "interested" (substring).
    (ReplyClassification.NOT_RELEVANT, ("not relevant", "not a fit", "no need", "unsubscribe",
                                        "remove me", "wrong person", "do not contact")),
    (ReplyClassification.NEGATIVE, ("not interested", "no thank", "no thanks", "we're all set",
                                    "already have", "decline")),
    (ReplyClassification.NOT_NOW, ("not right now", "not at the moment", "circle back", "next quarter",
                                   "later this year", "revisit", "reach out in")),
    (ReplyClassification.INTERESTED, ("interested", "sounds good", "keen", "would like to explore",
                                      "let's discuss", "happy to explore")),
    (ReplyClassification.POSITIVE, ("thank you", "thanks", "great", "appreciate")),
]


@dataclass
class ReplyClassificationResult:
    classification: ReplyClassification
    quote: str | None            # the grounding snippet from the actual message
    method: str = "deterministic"


def _find_quote(text: str, keyword: str) -> str:
    low = text.lower()
    idx = low.find(keyword)
    if idx < 0:
        return keyword
    start = max(0, idx - 30)
    end = min(len(text), idx + len(keyword) + 30)
    return text[start:end].strip()


def classify_reply(text: str | None) -> ReplyClassificationResult:
    """Deterministically classify a real inbound reply, grounded in a quote."""
    if not text or not text.strip():
        return ReplyClassificationResult(ReplyClassification.UNKNOWN, None)
    low = text.lower()
    for classification, keywords in _RULES:
        for kw in keywords:
            if kw in low:
                return ReplyClassificationResult(classification, _find_quote(text, kw))
    return ReplyClassificationResult(ReplyClassification.UNKNOWN, None)
