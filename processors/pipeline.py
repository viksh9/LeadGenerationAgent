"""End-to-end pipeline: collect → normalize → score → enrich → pitch."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session, sessionmaker

from collectors.base import Collector
from collectors.json_collector import JsonFileCollector
from database.models import Company, Lead
from database.repository import LeadRepository, create_session_factory, init_db
from enrichment.poc_finder import find_points_of_contact
from intelligence.lead_scorer import score_lead
from intelligence.opportunity_analyzer import analyze_opportunity
from intelligence.signal_detector import detect_signals
from outreach.pitch_generator import generate_pitch
from processors.normalizer import NormalizedLead, NormalizedSignal, normalize_record

logger = logging.getLogger(__name__)


class LeadGenerationPipeline:
    def __init__(
        self,
        collector: Collector | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self.collector = collector or JsonFileCollector()
        self.session_factory = session_factory or create_session_factory()
        bind = getattr(self.session_factory, "bind", None) or self.session_factory.kw.get("bind")
        init_db(bind)

    def run(self) -> list[Lead]:
        records = self.collector.collect()
        logger.info("pipeline_collect_complete source=%s count=%s", self.collector.name, len(records))
        lead_ids: list[int] = []
        with self.session_factory() as session:
            repo = LeadRepository(session)
            for record in records:
                normalized = normalize_record(record)
                if normalized is None:
                    logger.warning("skipping_invalid_record name=%s", getattr(record, "name", None))
                    continue
                try:
                    lead = self._process_one(repo, normalized)
                except Exception:
                    logger.exception("company_processing_failed name=%s", normalized.name)
                    raise
                lead_ids.append(lead.id)
                logger.info("company_processed name=%s lead_id=%s", normalized.name, lead.id)
            repo.commit()
            return [lead for lead_id in lead_ids if (lead := repo.get_lead(lead_id))]

    def _process_one(self, repo: LeadRepository, normalized: NormalizedLead) -> Lead:
        company = repo.upsert_company(
            name=normalized.name,
            domain=normalized.domain,
            industry=normalized.industry,
            size=normalized.size,
            location=normalized.location,
            description=normalized.description,
        )
        detected = detect_signals(normalized.signals)
        for item in detected:
            repo.add_signal(
                company,
                signal_type=item.signal_type,
                title=item.title,
                description=item.description,
                source=item.source,
                source_url=item.source_url,
                strength=item.strength,
                observed_at=item.observed_at,
            )
        scored = score_lead(detected)
        opportunity = analyze_opportunity(company_name=normalized.name, signals=detected)
        lead = repo.save_lead(
            company,
            score=scored.score,
            intent_level=scored.intent_level,
            opportunity_summary=opportunity.summary,
            recommended_motion=opportunity.recommended_motion,
        )
        contacts = find_points_of_contact(
            company_name=normalized.name,
            domain=normalized.domain,
            signals=detected,
            known_contacts=normalized.contacts,
        )
        stored_contacts = [
            repo.add_contact(
                company,
                full_name=contact.full_name,
                title=contact.title,
                email=contact.email,
                linkedin_url=contact.linkedin_url,
                seniority=contact.seniority,
                is_decision_maker=contact.is_decision_maker,
                confidence=contact.confidence,
            )
            for contact in contacts
        ]
        primary = next((c for c in stored_contacts if c.is_decision_maker), None)
        primary = primary or (stored_contacts[0] if stored_contacts else None)
        pitch = generate_pitch(
            company_name=normalized.name,
            opportunity=opportunity,
            score=scored,
            contact_name=primary.full_name if primary else None,
            contact_title=primary.title if primary else None,
        )
        repo.add_pitch(
            lead,
            contact_id=primary.id if primary else None,
            subject=pitch.subject,
            body=pitch.body,
            angle=pitch.angle,
        )
        return lead

    def process_company(self, company: Company) -> Lead:
        """Re-score an existing company from stored signals."""
        signals = [
            NormalizedSignal(
                signal_type=s.signal_type,
                title=s.title,
                description=s.description,
                source=s.source,
                source_url=s.source_url,
                strength=s.strength,
                observed_at=s.observed_at,
            )
            for s in company.signals
        ]
        detected = detect_signals(signals)
        scored = score_lead(detected)
        opportunity = analyze_opportunity(company_name=company.name, signals=detected)
        with self.session_factory() as session:
            repo = LeadRepository(session)
            lead = repo.save_lead(
                company,
                score=scored.score,
                intent_level=scored.intent_level,
                opportunity_summary=opportunity.summary,
                recommended_motion=opportunity.recommended_motion,
            )
            repo.commit()
            session.refresh(lead)
            return lead
