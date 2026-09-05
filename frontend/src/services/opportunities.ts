import type { Lead, LeadPriority } from '@/types/lead';
import type {
  Opportunity,
  OpportunityFilterState,
  OpportunitySortBy,
  OpportunitySummary,
  OpportunityType,
  OpportunityTypeDatum,
  StaffingNeed,
  Urgency,
} from '@/types/opportunity';

/**
 * Opportunities adapter.
 *
 * TEMPORARY STRATEGY (Phase 1): the backend has no Opportunity entity/endpoint.
 * Opportunities are derived here from persisted Lead data. `opportunity_type`,
 * `staffing_need` and `urgency` are DETERMINISTIC derivations of persisted
 * signal fields (documented below); score/priority/status/technologies/POC/
 * recommended_action are passed through unchanged. Opportunity confidence and a
 * team-size RANGE are not persisted and are never fabricated. When a dedicated
 * Opportunity API (or persisted opportunity_analysis) lands, only this file and
 * the hook change — components consume the typed Opportunity shape.
 */

export const OPPORTUNITY_TYPE_LABELS: Record<OpportunityType, string> = {
  NORMAL_HIRING: 'Normal Hiring',
  PROJECT_DRIVEN_HIRING: 'Project Driven Hiring',
  LARGE_SCALE_RAMP_UP: 'Large-Scale Ramp-Up',
  STAFF_AUGMENTATION: 'Staff Augmentation',
  VENDOR_OPPORTUNITY: 'Vendor Opportunity',
  TECHNOLOGY_IMPLEMENTATION: 'Technology Implementation',
  DIGITAL_TRANSFORMATION: 'Digital Transformation',
  LOW_CONFIDENCE: 'Low Confidence',
};

export const OPPORTUNITY_TYPES = Object.keys(OPPORTUNITY_TYPE_LABELS) as OpportunityType[];
export const STAFFING_NEEDS: StaffingNeed[] = ['HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'];
export const URGENCIES: Urgency[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'UNKNOWN'];

const DAY_MS = 86_400_000;
const URGENCY_RANK: Record<Urgency, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1, UNKNOWN: 0 };

/** Staffing need banded from the persisted estimated_hiring figure. */
export function deriveStaffingNeed(estimatedHiring: number | null | undefined): StaffingNeed {
  if (estimatedHiring == null || estimatedHiring <= 0) return 'UNKNOWN';
  if (estimatedHiring >= 25) return 'HIGH';
  if (estimatedHiring >= 10) return 'MEDIUM';
  return 'LOW';
}

/** Opportunity type derived from the detected signal_type + hiring size. */
export function deriveOpportunityType(lead: Lead): OpportunityType {
  const hiring = lead.estimated_hiring ?? 0;
  let base: OpportunityType;
  switch (lead.signal_type) {
    case 'HIRING':
      base = hiring >= 10 ? 'STAFF_AUGMENTATION' : 'NORMAL_HIRING';
      break;
    case 'PROJECT_AWARD':
    case 'PROJECT_EXECUTION':
      base = 'PROJECT_DRIVEN_HIRING';
      break;
    case 'EXPANSION':
      base = 'LARGE_SCALE_RAMP_UP';
      break;
    case 'DIGITAL_TRANSFORMATION':
      return 'DIGITAL_TRANSFORMATION';
    case 'TECHNOLOGY_INITIATIVE':
      return 'TECHNOLOGY_IMPLEMENTATION';
    case 'VENDOR_REQUIREMENT':
    case 'CONTRACT':
      return 'VENDOR_OPPORTUNITY';
    default:
      return 'LOW_CONFIDENCE';
  }
  // A large hiring figure escalates hiring/project types to a ramp-up.
  if (hiring >= 25) return 'LARGE_SCALE_RAMP_UP';
  return base;
}

/** Urgency derived from how recently the signal was observed (recency = urgency). */
export function deriveUrgency(
  signalDate: string | null | undefined,
  now: number,
): { urgency: Urgency; reason: string | null } {
  if (!signalDate) return { urgency: 'UNKNOWN', reason: null };
  const ts = new Date(signalDate).getTime();
  if (Number.isNaN(ts)) return { urgency: 'UNKNOWN', reason: null };
  const days = Math.max(0, Math.floor((now - ts) / DAY_MS));
  const reason = `Signal observed ${days === 0 ? 'today' : `${days} day${days === 1 ? '' : 's'} ago`}.`;
  if (days <= 7) return { urgency: 'CRITICAL', reason };
  if (days <= 30) return { urgency: 'HIGH', reason };
  if (days <= 60) return { urgency: 'MEDIUM', reason };
  return { urgency: 'LOW', reason };
}

/**
 * Deterministic Lead -> Opportunity mapping. `now` is injectable so urgency is
 * testable without depending on the wall clock.
 */
export function mapLeadToOpportunity(lead: Lead, now: number = Date.now()): Opportunity {
  const { urgency, reason } = deriveUrgency(lead.signal_date, now);
  return {
    leadId: lead.id,
    company: lead.company_name,
    industry: lead.industry,
    opportunityType: deriveOpportunityType(lead),
    businessReason: lead.opportunity_summary,
    staffingNeed: deriveStaffingNeed(lead.estimated_hiring),
    estimatedHiring: lead.estimated_hiring,
    urgency,
    urgencyReason: reason,
    technologies: lead.technologies ?? [],
    score: lead.lead_score,
    priority: lead.lead_priority,
    status: lead.status,
    confidence: null, // opportunity confidence is not persisted
    signalConfidence: lead.signal_confidence,
    pocRole: lead.poc_title,
    pocName: lead.poc_name,
    pocLinkedin: lead.poc_linkedin_url,
    recommendedAction: lead.recommended_action,
    signalType: lead.signal_type,
    signalTitle: lead.signal_title,
    signalDate: lead.signal_date,
    sourceName: lead.source_name,
    sourceUrl: lead.source_url,
    createdAt: lead.created_at,
  };
}

export function mapLeadsToOpportunities(leads: Lead[], now: number = Date.now()): Opportunity[] {
  return leads.map((lead) => mapLeadToOpportunity(lead, now));
}

// --- Filtering / sorting / aggregation -------------------------------------

export function filterOpportunities(
  opportunities: Opportunity[],
  f: OpportunityFilterState,
): Opportunity[] {
  const term = f.search.trim().toLowerCase();
  const tech = f.technology.trim().toLowerCase();
  const industry = f.industry.trim().toLowerCase();
  return opportunities.filter((o) => {
    if (f.type && o.opportunityType !== f.type) return false;
    if (f.priority && o.priority !== f.priority) return false;
    if (f.staffing && o.staffingNeed !== f.staffing) return false;
    if (f.urgency && o.urgency !== f.urgency) return false;
    if (f.status && o.status !== f.status) return false;
    if (industry && !(o.industry ?? '').toLowerCase().includes(industry)) return false;
    if (tech && !o.technologies.some((t) => t.toLowerCase().includes(tech))) return false;
    if (term) {
      const haystack = [
        o.company,
        o.signalTitle ?? '',
        OPPORTUNITY_TYPE_LABELS[o.opportunityType],
        o.technologies.join(' '),
        o.businessReason ?? '',
      ]
        .join(' ')
        .toLowerCase();
      if (!haystack.includes(term)) return false;
    }
    return true;
  });
}

export function sortOpportunities(opportunities: Opportunity[], sortBy: OpportunitySortBy): Opportunity[] {
  const copy = [...opportunities];
  switch (sortBy) {
    case 'urgency':
      return copy.sort((a, b) => URGENCY_RANK[b.urgency] - URGENCY_RANK[a.urgency] || b.score - a.score);
    case 'team':
      return copy.sort((a, b) => (b.estimatedHiring ?? -1) - (a.estimatedHiring ?? -1));
    case 'signal_date':
      return copy.sort((a, b) => (b.signalDate ?? '').localeCompare(a.signalDate ?? ''));
    case 'created':
      return copy.sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? ''));
    case 'score':
    default:
      return copy.sort((a, b) => b.score - a.score);
  }
}

export function buildOpportunitySummary(opportunities: Opportunity[]): OpportunitySummary {
  return {
    total: opportunities.length,
    hot: opportunities.filter((o) => o.priority === 'HOT').length,
    highStaffing: opportunities.filter((o) => o.staffingNeed === 'HIGH').length,
    highUrgency: opportunities.filter((o) => o.urgency === 'HIGH' || o.urgency === 'CRITICAL').length,
    qualified: opportunities.filter((o) => o.status === 'QUALIFIED').length,
  };
}

export function buildTypeDistribution(opportunities: Opportunity[]): OpportunityTypeDatum[] {
  const counts = new Map<OpportunityType, number>();
  for (const o of opportunities) counts.set(o.opportunityType, (counts.get(o.opportunityType) ?? 0) + 1);
  return OPPORTUNITY_TYPES.map((type) => ({
    type,
    label: OPPORTUNITY_TYPE_LABELS[type],
    count: counts.get(type) ?? 0,
  })).filter((d) => d.count > 0);
}

export const PRIORITIES: LeadPriority[] = ['HOT', 'WARM', 'NURTURE', 'LOW'];
