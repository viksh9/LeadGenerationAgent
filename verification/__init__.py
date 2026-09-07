"""Evidence Verification & Source Confidence Engine.

Answers: "How confident are we that this business signal is real, current,
relevant, and supported by reliable evidence?" — while keeping FOUR distinct
numbers separate: source reliability, evidence confidence, signal confidence, and
the commercial lead score. Deterministic, explainable, no LLM.
"""

from verification.service import EvidenceVerificationService  # noqa: F401
from verification.signal_verification import SignalVerificationResult, verify_evidence_set  # noqa: F401
