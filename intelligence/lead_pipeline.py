"""End-to-end Lead Analysis Pipeline.

Orchestrates the existing engines into a single flow — it contains no business
rules of its own, only normalization, sequencing, result assembly, and
persistence:

    raw lead
      -> normalize
      -> SignalDetector
      -> OpportunityAnalyzer
      -> LeadScorer
      -> POCFinder
      -> PitchGenerator
      -> LeadAnalysisResult
      -> persist (Lead)

Independent of FastAPI (no routes, no request objects) so a future
``POST /leads/analyze`` can call it directly. Synchronous and lightweight — no
queues, network, or LLM calls.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from config.exceptions import AppError, NotFoundError
from database.models import LeadPriority, LeadStatus, SignalType, utcnow
from database.repository import (
    create_lead,
    create_session_factory,
    find_duplicate_lead,
    get_lead,
    update_lead,
)
from enrichment.poc_finder import POCFinder, POCRecommendationResult
from intelligence.lead_scorer import LeadScorer, LeadScoreResult
from intelligence.opportunity_analyzer import OpportunityAnalyzer, OpportunityAssessment
from intelligence.signal_detector import (
    SignalDetectionInput,
    SignalDetectionResult,
    SignalDetector,
)
from outreach.pitch_generator import PitchGenerationResult, PitchGenerator

logger = logging.getLogger(__name__)


class LeadPipelineError(AppError):
    """A lead-analysis stage failed. Carries the stage name, not internal detail."""

    def __init__(self, message: str, *, stage: Optional[str] = None) -> None:
        super().__init__(message, status_code=500, code="pipeline_error")
        self.stage = stage


# ---------------------------------------------------------------------------
# Input normalization
# ---------------------------------------------------------------------------


class NormalizedLead(BaseModel):
    """Cleaned lead input. The original payload is never mutated."""

    company_name: str
    industry: Optional[str] = None
    location: Optional[str] = None
    company_size: Optional[str] = None
    company_website: Optional[str] = None
    signal_title: Optional[str] = None
    signal_description: Optional[str] = None
    signal_date: Optional[datetime] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)
    project_name: Optional[str] = None
    project_value: Optional[float] = None
    estimated_hiring: Optional[int] = None
    hiring_roles: list[str] = Field(default_factory=list)
    poc_name: Optional[str] = None
    poc_title: Optional[str] = None
    poc_linkedin_url: Optional[str] = None
    public_contact: Optional[str] = None
    signal_confidence: Optional[float] = None


def _get(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _clean_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dedupe(values: Any) -> list[str]:
    """Trim, drop empties, and remove case-insensitive duplicates (order kept)."""
    if not values:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        text = str(item).strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            result.append(text)
    return result


def normalize_lead(raw_lead: Any) -> NormalizedLead:
    """Normalize a raw lead without altering the original payload."""
    company_name = _clean_str(_get(raw_lead, "company_name"))
    if not company_name:
        raise LeadPipelineError("Lead analysis failed during normalization: company_name is required.", stage="normalization")

    return NormalizedLead(
        company_name=company_name,
        industry=_clean_str(_get(raw_lead, "industry")),
        location=_clean_str(_get(raw_lead, "location")),
        company_size=_clean_str(_get(raw_lead, "company_size")),
        company_website=_clean_str(_get(raw_lead, "company_website")),
        signal_title=_clean_str(_get(raw_lead, "signal_title")),
        signal_description=_clean_str(_get(raw_lead, "signal_description")),
        signal_date=_get(raw_lead, "signal_date"),
        source_name=_clean_str(_get(raw_lead, "source_name")),
        source_url=_clean_str(_get(raw_lead, "source_url")),
        technologies=_dedupe(_get(raw_lead, "technologies")),
        project_name=_clean_str(_get(raw_lead, "project_name")),
        project_value=_get(raw_lead, "project_value"),
        estimated_hiring=_get(raw_lead, "estimated_hiring"),
        hiring_roles=_dedupe(_get(raw_lead, "hiring_roles")),
        poc_name=_clean_str(_get(raw_lead, "poc_name")),
        poc_title=_clean_str(_get(raw_lead, "poc_title")),
        poc_linkedin_url=_clean_str(_get(raw_lead, "poc_linkedin_url")),
        public_contact=_clean_str(_get(raw_lead, "public_contact")),
        signal_confidence=_get(raw_lead, "signal_confidence"),
    )


# ---------------------------------------------------------------------------
# Result model (frontend-friendly; nested engine outputs serialize to JSON)
# ---------------------------------------------------------------------------


class LeadAnalysisResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lead_id: Optional[int] = None
    company_name: str
    lead_input: dict[str, Any] = Field(default_factory=dict)
    normalized_data: dict[str, Any] = Field(default_factory=dict)
    signal_analysis: SignalDetectionResult
    opportunity_analysis: OpportunityAssessment
    scoring_result: LeadScoreResult
    poc_recommendation: POCRecommendationResult
    pitch_result: PitchGenerationResult
    final_score: int
    priority: LeadPriority
    recommended_action: Optional[str] = None
    status: str = LeadStatus.NEW.value
    already_existed: bool = False


def _to_plain(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, Mapping):
        return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in obj.items()}
    return {}


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class LeadAnalysisPipeline:
    """Orchestrates the analysis engines and persists the calculated lead.

    Duplicate strategy (Phase 1): a lead matching an existing row on
    (company_name, signal_title, source_url) UPDATES that row (an upsert /
    re-analysis) rather than creating a new one — never a silent duplicate.
    """

    def __init__(
        self,
        detector: Optional[SignalDetector] = None,
        analyzer: Optional[OpportunityAnalyzer] = None,
        scorer: Optional[LeadScorer] = None,
        poc_finder: Optional[POCFinder] = None,
        pitcher: Optional[PitchGenerator] = None,
    ) -> None:
        self.detector = detector or SignalDetector()
        self.analyzer = analyzer or OpportunityAnalyzer()
        self.scorer = scorer or LeadScorer()
        self.poc_finder = poc_finder or POCFinder()
        self.pitcher = pitcher or PitchGenerator()

    # -- public API ---------------------------------------------------------

    def analyze(
        self,
        raw_lead: Any,
        session: Optional[Session] = None,
        *,
        persist: bool = True,
        existing_id: Optional[int] = None,
    ) -> LeadAnalysisResult:
        """Run the full pipeline on a raw lead and (optionally) persist it."""
        normalized = self._run("normalization", lambda: normalize_lead(raw_lead))
        company = normalized.company_name
        logger.info("pipeline_started company=%s", company)
        logger.info("normalization_completed company=%s", company)

        signal = self._run("signal detection", lambda: self.detector.detect(self._signal_input(normalized)))
        logger.info("signals_detected company=%s types=%s", company, [t.value for t in signal.signal_types])

        opportunity = self._run("opportunity analysis", lambda: self.analyzer.analyze(normalized, signal))
        logger.info("opportunity_analyzed company=%s type=%s", company, opportunity.opportunity_type.value)

        score = self._run("lead scoring", lambda: self.scorer.score(normalized, signal, opportunity))
        logger.info("lead_scored company=%s score=%s priority=%s", company, score.score, score.priority.value)

        poc = self._run("POC recommendation", lambda: self.poc_finder.recommend(normalized, signal, opportunity))
        primary_role = poc.primary_role.role if poc.primary_role else None
        logger.info("poc_recommended company=%s primary_role=%s", company, primary_role)

        pitch = self._run("pitch generation", lambda: self.pitcher.generate(normalized, signal, opportunity, poc, score))
        logger.info("pitch_generated company=%s strategy=%s", company, pitch.message_strategy.value)

        result = self._build_result(raw_lead, normalized, signal, opportunity, score, poc, pitch)

        if persist:
            lead_id, existed = self._persist_lead(
                session, normalized, signal, opportunity, score, poc, pitch, existing_id
            )
            result.lead_id = lead_id
            result.already_existed = existed

        logger.info("pipeline_completed company=%s lead_id=%s", company, result.lead_id)
        return result

    def reanalyze(self, session: Session, lead_id: int) -> LeadAnalysisResult:
        """Re-run analysis on an existing lead, refreshing all derived fields.

        Preserves lifecycle fields (e.g. ``status``) and updates
        ``last_verified_at`` / ``updated_at``.
        """
        lead = get_lead(session, lead_id)
        if lead is None:
            raise NotFoundError(f"Lead {lead_id} was not found")
        logger.info("reanalysis_started lead_id=%s company=%s", lead_id, lead.company_name)
        return self.analyze(self._lead_to_raw(lead), session=session, persist=True, existing_id=lead_id)

    # -- stage plumbing -----------------------------------------------------

    @staticmethod
    def _run(stage: str, fn):
        try:
            return fn()
        except LeadPipelineError:
            raise
        except Exception as exc:  # noqa: BLE001 — translate to a safe stage error
            logger.exception("pipeline_failed stage=%s", stage)
            raise LeadPipelineError(f"Lead analysis failed during {stage}.", stage=stage) from exc

    @staticmethod
    def _signal_input(normalized: NormalizedLead) -> SignalDetectionInput:
        return SignalDetectionInput(
            signal_title=normalized.signal_title,
            signal_description=normalized.signal_description,
            technologies=list(normalized.technologies),
            hiring_roles=list(normalized.hiring_roles),
            estimated_hiring=normalized.estimated_hiring,
            industry=normalized.industry,
            project_name=normalized.project_name,
            project_value=normalized.project_value,
            source_name=normalized.source_name,
        )

    def _build_result(
        self,
        raw_lead: Any,
        normalized: NormalizedLead,
        signal: SignalDetectionResult,
        opportunity: OpportunityAssessment,
        score: LeadScoreResult,
        poc: POCRecommendationResult,
        pitch: PitchGenerationResult,
    ) -> LeadAnalysisResult:
        return LeadAnalysisResult(
            company_name=normalized.company_name,
            lead_input=_to_plain(raw_lead),
            normalized_data=normalized.model_dump(mode="json"),
            signal_analysis=signal,
            opportunity_analysis=opportunity,
            scoring_result=score,
            poc_recommendation=poc,
            pitch_result=pitch,
            final_score=score.score,
            priority=score.priority,
            recommended_action=opportunity.recommended_next_step,
            status=LeadStatus.NEW.value,
        )

    # -- persistence --------------------------------------------------------

    def _lead_fields(
        self,
        normalized: NormalizedLead,
        signal: SignalDetectionResult,
        opportunity: OpportunityAssessment,
        score: LeadScoreResult,
        poc: POCRecommendationResult,
        pitch: PitchGenerationResult,
    ) -> dict[str, Any]:
        primary_signal = signal.signal_types[0] if signal.signal_types else SignalType.OTHER
        estimated = signal.estimated_hiring if signal.estimated_hiring is not None else normalized.estimated_hiring
        hiring_roles = signal.detected_roles or list(normalized.hiring_roles)
        confidence = (
            normalized.signal_confidence
            if normalized.signal_confidence is not None
            else float(signal.signal_strength)
        )
        primary_role = poc.primary_role.role if poc.primary_role else None
        return {
            "company_name": normalized.company_name,
            "industry": normalized.industry,
            "location": normalized.location,
            "company_size": normalized.company_size,
            "company_website": normalized.company_website,
            "signal_type": primary_signal,
            "signal_title": normalized.signal_title,
            "signal_description": normalized.signal_description,
            "signal_date": normalized.signal_date,
            "source_name": normalized.source_name,
            "source_url": normalized.source_url,
            "technologies": list(signal.detected_technologies),
            "project_name": normalized.project_name,
            "project_value": normalized.project_value,
            "estimated_hiring": estimated,
            "hiring_roles": hiring_roles,
            "poc_name": normalized.poc_name,
            "poc_title": normalized.poc_title or primary_role,
            "poc_linkedin_url": normalized.poc_linkedin_url,
            "public_contact": normalized.public_contact,
            "signal_confidence": confidence,
            "lead_score": float(score.score),
            "lead_priority": score.priority,
            "opportunity_summary": opportunity.business_reason,
            "recommended_action": opportunity.recommended_next_step,
            "recommended_pitch": f"Subject: {pitch.email_subject}\n\n{pitch.recommended_pitch}",
            "status": LeadStatus.NEW,
        }

    def _persist_lead(
        self,
        session: Optional[Session],
        normalized: NormalizedLead,
        signal: SignalDetectionResult,
        opportunity: OpportunityAssessment,
        score: LeadScoreResult,
        poc: POCRecommendationResult,
        pitch: PitchGenerationResult,
        existing_id: Optional[int],
    ) -> tuple[int, bool]:
        own_session = False
        if session is None:
            session = create_session_factory()()
            own_session = True
        try:
            fields = self._lead_fields(normalized, signal, opportunity, score, poc, pitch)
            target_id = existing_id
            if target_id is None:
                dup = find_duplicate_lead(
                    session,
                    company_name=normalized.company_name,
                    signal_title=normalized.signal_title,
                    source_url=normalized.source_url,
                )
                target_id = dup.id if dup else None

            if target_id is not None:
                # Re-analysis / upsert: refresh derived fields, keep lifecycle status.
                updates = {k: v for k, v in fields.items() if k != "status"}
                updates["last_verified_at"] = utcnow()
                update_lead(session, target_id, **updates)
                logger.info("lead_persisted company=%s lead_id=%s existed=True", normalized.company_name, target_id)
                return target_id, True

            lead = create_lead(session, **fields)
            logger.info("lead_persisted company=%s lead_id=%s existed=False", normalized.company_name, lead.id)
            return lead.id, False
        except LeadPipelineError:
            raise
        except Exception as exc:  # noqa: BLE001
            try:
                session.rollback()
            except Exception:  # pragma: no cover - defensive
                pass
            logger.exception("pipeline_failed stage=persistence")
            raise LeadPipelineError(
                "Lead analysis failed during database persistence.", stage="persistence"
            ) from exc
        finally:
            if own_session:
                session.close()

    @staticmethod
    def _lead_to_raw(lead) -> dict[str, Any]:
        return {
            "company_name": lead.company_name,
            "industry": lead.industry,
            "location": lead.location,
            "company_size": lead.company_size,
            "company_website": lead.company_website,
            "signal_title": lead.signal_title,
            "signal_description": lead.signal_description,
            "signal_date": lead.signal_date,
            "source_name": lead.source_name,
            "source_url": lead.source_url,
            "technologies": list(lead.technologies or []),
            "project_name": lead.project_name,
            "project_value": lead.project_value,
            "estimated_hiring": lead.estimated_hiring,
            "hiring_roles": list(lead.hiring_roles or []),
            "poc_name": lead.poc_name,
            "poc_title": lead.poc_title,
            "poc_linkedin_url": lead.poc_linkedin_url,
            "public_contact": lead.public_contact,
            "signal_confidence": lead.signal_confidence,
        }


def analyze_lead(raw_lead: Any, session: Optional[Session] = None, *, persist: bool = True) -> LeadAnalysisResult:
    """Convenience wrapper using a default-configured pipeline."""
    return LeadAnalysisPipeline().analyze(raw_lead, session, persist=persist)
