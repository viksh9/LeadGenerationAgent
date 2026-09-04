"""Identify likely decision-makers from known contacts and signal context."""

from dataclasses import dataclass
from typing import Any

from intelligence.signal_detector import DetectedSignal

DECISION_TITLES = {
    "ceo": ("c-level", True, 0.95),
    "chief": ("c-level", True, 0.9),
    "founder": ("c-level", True, 0.92),
    "president": ("c-level", True, 0.88),
    "cto": ("c-level", True, 0.93),
    "cio": ("c-level", True, 0.93),
    "cfo": ("c-level", True, 0.85),
    "vp": ("vp", True, 0.82),
    "vice president": ("vp", True, 0.82),
    "head of": ("director", True, 0.78),
    "director": ("director", True, 0.7),
    "manager": ("manager", False, 0.45),
}

ROLE_HINTS = {
    "hiring": ("Head of Engineering", "director", True, 0.55),
    "project": ("VP of Operations", "vp", True, 0.6),
    "funding": ("Chief Executive Officer", "c-level", True, 0.58),
    "tech_stack": ("Chief Technology Officer", "c-level", True, 0.62),
    "expansion": ("VP of Growth", "vp", True, 0.5),
    "leadership": ("Chief of Staff", "director", False, 0.4),
}


@dataclass
class PointOfContact:
    full_name: str
    title: str | None
    email: str | None
    linkedin_url: str | None
    seniority: str
    is_decision_maker: bool
    confidence: float


def _classify_title(title: str | None) -> tuple[str, bool, float]:
    lowered = (title or "").lower()
    for needle, result in DECISION_TITLES.items():
        if needle in lowered:
            return result
    return ("unknown", False, 0.3)


def _synthetic_email(name: str, domain: str | None) -> str | None:
    if not domain:
        return None
    parts = [p for p in name.lower().replace(".", "").split() if p.isalpha() or p.replace("-", "").isalpha()]
    if len(parts) < 2:
        return None
    return f"{parts[0]}.{parts[-1]}@{domain}"


def find_points_of_contact(
    company_name: str,
    domain: str | None,
    signals: list[DetectedSignal],
    known_contacts: list[dict[str, Any]] | None = None,
) -> list[PointOfContact]:
    contacts: list[PointOfContact] = []
    for raw in known_contacts or []:
        name = (raw.get("full_name") or "").strip()
        if not name:
            continue
        seniority, is_dm, confidence = _classify_title(raw.get("title"))
        if raw.get("is_decision_maker") is True:
            is_dm = True
            confidence = max(confidence, 0.8)
        if raw.get("seniority"):
            seniority = raw["seniority"]
        contacts.append(
            PointOfContact(
                full_name=name,
                title=raw.get("title"),
                email=raw.get("email") or _synthetic_email(name, domain),
                linkedin_url=raw.get("linkedin_url"),
                seniority=seniority,
                is_decision_maker=is_dm,
                confidence=float(raw.get("confidence") or confidence),
            )
        )

    if not contacts:
        types = {s.signal_type for s in signals} or {"hiring"}
        primary_type = next((t for t in ("project", "funding", "tech_stack", "hiring") if t in types), "hiring")
        title, seniority, is_dm, confidence = ROLE_HINTS[primary_type]
        placeholder_name = f"{company_name} {title}"
        contacts.append(
            PointOfContact(
                full_name=placeholder_name,
                title=title,
                email=None,
                linkedin_url=None,
                seniority=seniority,
                is_decision_maker=is_dm,
                confidence=confidence,
            )
        )

    contacts.sort(key=lambda c: (c.is_decision_maker, c.confidence), reverse=True)
    return contacts
