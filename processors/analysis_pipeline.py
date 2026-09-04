"""Lead analysis pipeline: raw signal -> calculated lead.

Orchestrates the deterministic intelligence engines and maps their outputs onto
the flat ``Lead`` fields and the ``LeadAnalyzeResponse`` API schema:

    LeadAnalyzeRequest
        -> SignalDetector      (signals, technologies, hiring)
        -> OpportunityAnalyzer  (opportunity type, staffing, urgency)
        -> LeadScorer           (lead_score, priority)
        -> POCFinder            (decision-maker role recommendation)
        -> calculated Lead (optionally persisted) + LeadAnalyzeResponse

This is the integration layer, so — unlike the individual engines — it may
depend on the API schemas and the database repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from api.schemas import (
    AnalyzedSignal,
    LeadAnalyzeRequest,
    LeadAnalyzeResponse,
    LeadResponse,
    OpportunityAnalysis,
    POCRecommendation,
    ScoreComponent,
)
from database.models import LeadStatus, SignalType
from database.repository import create_lead
from enrichment.poc_finder import POCFinder, POCRecommendationResult
from intelligence.lead_scorer import LeadScorer, LeadScoreResult
from intelligence.opportunity_analyzer import OpportunityAnalyzer, OpportunityAssessment
from intelligence.signal_detector import (
    SignalDetectionInput,
    SignalDetectionResult,
    SignalDetector,
)
from outreach.pitch_generator import PitchGenerationResult, PitchGenerator


@dataclass
class AnalysisArtifacts:
    """Raw engine outputs plus the derived ``Lead`` column values."""

    signal: SignalDetectionResult
    opportunity: OpportunityAssessment
    score: LeadScoreResult
    poc: POCRecommendationResult
    pitch: PitchGenerationResult
    lead_fields: dict[str, Any]


class AnalysisPipeline:
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

    # -- core orchestration -------------------------------------------------

    def run(self, request: "LeadAnalyzeRequest | dict") -> AnalysisArtifacts:
        if isinstance(request, dict):
            request = LeadAnalyzeRequest(**request)

        signal = self.detector.detect(
            SignalDetectionInput(
                signal_title=request.signal_title,
                signal_description=request.signal_description,
                technologies=list(request.technologies or []),
                hiring_roles=list(request.hiring_roles or []),
                estimated_hiring=request.estimated_hiring,
                industry=request.industry,
                project_name=request.project_name,
                project_value=request.project_value,
                source_name=request.source_name,
            )
        )
        opportunity = self.analyzer.analyze(request, signal)
        score = self.scorer.score(request, signal, opportunity)
        poc = self.poc_finder.recommend(request, signal, opportunity)
        pitch = self.pitcher.generate(request, signal, opportunity, poc, score)

        lead_fields = self._lead_fields(request, signal, opportunity, score, poc, pitch)
        return AnalysisArtifacts(
            signal=signal,
            opportunity=opportunity,
            score=score,
            poc=poc,
            pitch=pitch,
            lead_fields=lead_fields,
        )

    def analyze(self, request: "LeadAnalyzeRequest | dict") -> LeadAnalyzeResponse:
        """Analyze without persisting (the response lead carries id=0)."""
        artifacts = self.run(request)
        preview_lead = LeadResponse(id=0, **artifacts.lead_fields)
        return self._to_response(artifacts, preview_lead)

    def analyze_and_store(
        self, session: Session, request: "LeadAnalyzeRequest | dict"
    ) -> LeadAnalyzeResponse:
        """Analyze and persist the calculated lead, returning the stored view."""
        artifacts = self.run(request)
        lead = create_lead(session, **artifacts.lead_fields)
        return self._to_response(artifacts, LeadResponse.model_validate(lead))

    # -- mapping: engine outputs -> Lead columns ----------------------------

    def _lead_fields(
        self,
        request: LeadAnalyzeRequest,
        signal: SignalDetectionResult,
        opportunity: OpportunityAssessment,
        score: LeadScoreResult,
        poc: POCRecommendationResult,
        pitch: PitchGenerationResult,
    ) -> dict[str, Any]:
        primary_signal = signal.signal_types[0] if signal.signal_types else SignalType.OTHER
        estimated = signal.estimated_hiring if signal.estimated_hiring is not None else request.estimated_hiring
        hiring_roles = signal.detected_roles or list(request.hiring_roles or [])
        confidence = (
            request.signal_confidence
            if request.signal_confidence is not None
            else float(signal.signal_strength)
        )

        primary_role = poc.primary_role.role if poc.primary_role else None
        poc_name = request.poc_name  # POCFinder recommends roles, not real people
        poc_title = request.poc_title or primary_role
        poc_linkedin = request.poc_linkedin_url

        return {
            "company_name": request.company_name,
            "industry": request.industry,
            "location": request.location,
            "company_size": request.company_size,
            "company_website": request.company_website,
            "signal_type": primary_signal,
            "signal_title": request.signal_title,
            "signal_description": request.signal_description,
            "signal_date": request.signal_date,
            "source_name": request.source_name,
            "source_url": request.source_url,
            "technologies": list(signal.detected_technologies),
            "project_name": request.project_name,
            "project_value": request.project_value,
            "estimated_hiring": estimated,
            "hiring_roles": hiring_roles,
            "poc_name": poc_name,
            "poc_title": poc_title,
            "poc_linkedin_url": poc_linkedin,
            "public_contact": request.public_contact,
            "signal_confidence": confidence,
            "lead_score": float(score.score),
            "lead_priority": score.priority,
            "opportunity_summary": opportunity.business_reason,
            "recommended_action": opportunity.recommended_next_step,
            "recommended_pitch": f"Subject: {pitch.email_subject}\n\n{pitch.recommended_pitch}",
            "status": LeadStatus.NEW,
        }

    # -- mapping: engine outputs -> API response ----------------------------

    def _to_response(
        self, artifacts: AnalysisArtifacts, lead: LeadResponse
    ) -> LeadAnalyzeResponse:
        signal, opportunity, score, poc = (
            artifacts.signal,
            artifacts.opportunity,
            artifacts.score,
            artifacts.poc,
        )

        signals_detected = [
            AnalyzedSignal(
                signal_type=detail.signal_type,
                title=detail.signal_type.value.replace("_", " ").title(),
                description=detail.reason,
                strength=float(signal.signal_strength),
                intent_tags=detail.detected_keywords,
            )
            for detail in signal.signals
        ]

        opportunity_analysis = OpportunityAnalysis(
            summary=opportunity.business_reason,
            recommended_motion=opportunity.recommended_next_step,
            primary_stage=opportunity.opportunity_type.value,
            pain_hypotheses=[],
        )

        poc_recommendation = self._poc_recommendation(poc)

        return LeadAnalyzeResponse(
            lead=lead,
            signals_detected=signals_detected,
            opportunity_analysis=opportunity_analysis,
            poc_recommendation=poc_recommendation,
            score=float(score.score),
            priority=score.priority,
            score_breakdown=[
                ScoreComponent(label=label, points=float(points))
                for label, points in score.score_breakdown.items()
            ],
            recommended_action=opportunity.recommended_next_step,
            recommended_pitch=f"Subject: {artifacts.pitch.email_subject}\n\n{artifacts.pitch.recommended_pitch}",
        )

    @staticmethod
    def _poc_recommendation(poc: POCRecommendationResult) -> Optional[POCRecommendation]:
        primary = poc.primary_role
        if primary is None:
            return None
        return POCRecommendation(
            full_name=primary.role,  # a recommended role, not a real person
            title=primary.role,
            seniority=primary.decision_maker_type.value,
            is_decision_maker=True,
            confidence=round(primary.relevance_score / 100.0, 2),
        )


def run_analysis(request: "LeadAnalyzeRequest | dict") -> LeadAnalyzeResponse:
    """Convenience wrapper: analyze without persisting."""
    return AnalysisPipeline().analyze(request)
