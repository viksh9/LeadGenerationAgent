import type { Lead, LeadPriority } from '@/types/lead';
import type {
  CompanyContactGroup,
  ContactConfidence,
  ContactFilterState,
  ContactRecommendation,
  ContactSortBy,
  ContactSummary,
  DecisionMakerType,
  TopTargetRole,
} from '@/types/contact';
import {
  OPPORTUNITY_TYPE_LABELS,
  deriveOpportunityType,
  deriveStaffingNeed,
  deriveUrgency,
} from '@/services/opportunities';

/**
 * Contacts adapter.
 *
 * TEMPORARY STRATEGY (Phase 1): there is no Contact/Person backend entity. The
 * pipeline persists a recommended decision-maker ROLE (`poc_title`) per lead —
 * not a verified person. This adapter maps each lead with a recommended role to
 * a `ContactRecommendation`.
 *
 * - `role` / `personName` / `linkedinUrl` come straight from the lead
 *   (personName is null unless the backend actually names someone).
 * - `decisionMakerType` is a documented deterministic mapping of the role text.
 * - `relevance` reuses the related LEAD SCORE as the Phase-1 proxy (the POC
 *   engine's per-role relevance/confidence is not persisted). We do NOT invent a
 *   new score — see docs/frontend-contacts.md.
 * - `reason` (POC explanation) is not persisted, so it is null ("Not available").
 *
 * When a Contact entity lands, only this file and the hook change.
 */

export const DECISION_MAKER_TYPE_LABELS: Record<DecisionMakerType, string> = {
  TECHNICAL: 'Technical',
  BUSINESS: 'Business',
  DELIVERY: 'Delivery',
  PROCUREMENT: 'Procurement',
  VENDOR: 'Vendor Management',
  HR: 'HR / Talent',
};

export const DECISION_MAKER_TYPES = Object.keys(DECISION_MAKER_TYPE_LABELS) as DecisionMakerType[];
export const CONFIDENCE_LEVELS: ContactConfidence[] = ['HIGH', 'MEDIUM', 'LOW'];

const PRIORITY_RANK: Record<LeadPriority, number> = { HOT: 3, WARM: 2, NURTURE: 1, LOW: 0 };

/** Map a role title to a decision-maker category (keyword rules, documented). */
export function deriveDecisionMakerType(role: string): DecisionMakerType {
  const r = role.toLowerCase();
  if (/(procurement|sourcing|purchasing)/.test(r)) return 'PROCUREMENT';
  if (/vendor/.test(r)) return 'VENDOR';
  if (/(talent|recruit|people|hr\b|human resources)/.test(r)) return 'HR';
  if (/(delivery|program|pmo|project director|programme)/.test(r)) return 'DELIVERY';
  if (/(cto|cio|engineering|technology|technical|architect|developer|devops|platform|data|software)/.test(r))
    return 'TECHNICAL';
  if (/(ceo|coo|cfo|business|operations|sales|marketing|finance|commercial)/.test(r)) return 'BUSINESS';
  return 'BUSINESS';
}

/** Relevance band per the documented thresholds (§9). */
export function relevanceBand(relevance: number): ContactConfidence {
  if (relevance >= 80) return 'HIGH';
  if (relevance >= 60) return 'MEDIUM';
  return 'LOW';
}

/**
 * Derive contact recommendations from a lead. Returns an array (Phase 1 yields
 * 0 or 1) to match the future multi-role shape. `now` is injectable for testing.
 */
export function mapLeadToContactRecommendations(lead: Lead, now: number = Date.now()): ContactRecommendation[] {
  const role = lead.poc_title;
  if (!role) return []; // no recommended role -> no contact recommendation

  const relevance = lead.lead_score;
  const { urgency, reason } = deriveUrgency(lead.signal_date, now);
  return [
    {
      id: `${lead.id}:${role}`,
      leadId: lead.id,
      company: lead.company_name,
      industry: lead.industry,
      location: lead.location,
      role,
      personName: lead.poc_name,
      linkedinUrl: lead.poc_linkedin_url,
      publicContact: lead.public_contact,
      decisionMakerType: deriveDecisionMakerType(role),
      relevance,
      confidence: relevanceBand(relevance),
      reason: null, // POC engine reason is not persisted
      recommendedAction: lead.recommended_action,
      opportunityType: deriveOpportunityType(lead),
      opportunitySummary: lead.opportunity_summary,
      staffingNeed: deriveStaffingNeed(lead.estimated_hiring),
      urgency,
      urgencyReason: reason,
      estimatedHiring: lead.estimated_hiring,
      leadScore: lead.lead_score,
      priority: lead.lead_priority,
      status: lead.status,
      signalType: lead.signal_type,
      signalTitle: lead.signal_title,
      signalDate: lead.signal_date,
      sourceName: lead.source_name,
      sourceUrl: lead.source_url,
      signalConfidence: lead.signal_confidence,
      updatedAt: lead.updated_at,
      source: 'LEAD_INTELLIGENCE',
    },
  ];
}

/**
 * Map many leads to contact recommendations, de-duplicating the same role for
 * the same company (keeps the highest-relevance one) so summaries and groups do
 * not double-count (§5/§21).
 */
export function mapLeadsToContacts(leads: Lead[], now: number = Date.now()): ContactRecommendation[] {
  const all = leads.flatMap((lead) => mapLeadToContactRecommendations(lead, now));
  const byKey = new Map<string, ContactRecommendation>();
  for (const c of all) {
    const key = `${c.company}::${c.role}`;
    const existing = byKey.get(key);
    if (!existing || c.relevance > existing.relevance) byKey.set(key, c);
  }
  return Array.from(byKey.values());
}

export function opportunityLabel(c: ContactRecommendation): string {
  return OPPORTUNITY_TYPE_LABELS[c.opportunityType];
}

// --- Filtering / sorting / aggregation -------------------------------------

export function filterContacts(contacts: ContactRecommendation[], f: ContactFilterState): ContactRecommendation[] {
  const term = f.search.trim().toLowerCase();
  const role = f.role.trim().toLowerCase();
  const industry = f.industry.trim().toLowerCase();
  const min = f.minRelevance === '' ? null : Number(f.minRelevance);
  return contacts.filter((c) => {
    if (f.type && c.decisionMakerType !== f.type) return false;
    if (f.priority && c.priority !== f.priority) return false;
    if (f.opportunityType && c.opportunityType !== f.opportunityType) return false;
    if (f.confidence && c.confidence !== f.confidence) return false;
    if (min != null && Number.isFinite(min) && c.relevance < min) return false;
    if (role && !c.role.toLowerCase().includes(role)) return false;
    if (industry && !(c.industry ?? '').toLowerCase().includes(industry)) return false;
    if (term) {
      const haystack = `${c.company} ${c.role} ${c.industry ?? ''}`.toLowerCase();
      if (!haystack.includes(term)) return false;
    }
    return true;
  });
}

export function sortContacts(contacts: ContactRecommendation[], sortBy: ContactSortBy): ContactRecommendation[] {
  const copy = [...contacts];
  switch (sortBy) {
    case 'company':
      return copy.sort((a, b) => a.company.localeCompare(b.company) || b.relevance - a.relevance);
    case 'lead_score':
      return copy.sort((a, b) => b.leadScore - a.leadScore);
    case 'priority':
      return copy.sort((a, b) => PRIORITY_RANK[b.priority] - PRIORITY_RANK[a.priority] || b.relevance - a.relevance);
    case 'updated':
      return copy.sort((a, b) => (b.updatedAt ?? '').localeCompare(a.updatedAt ?? ''));
    case 'relevance':
    default:
      return copy.sort((a, b) => b.relevance - a.relevance);
  }
}

export function buildContactSummary(contacts: ContactRecommendation[]): ContactSummary {
  return {
    total: contacts.length,
    highRelevance: contacts.filter((c) => c.confidence === 'HIGH').length,
    technical: contacts.filter((c) => c.decisionMakerType === 'TECHNICAL').length,
    procurementVendor: contacts.filter(
      (c) => c.decisionMakerType === 'PROCUREMENT' || c.decisionMakerType === 'VENDOR',
    ).length,
  };
}

/** Most-recommended roles with average relevance (§23). */
export function buildTopTargetRoles(contacts: ContactRecommendation[], limit = 6): TopTargetRole[] {
  const map = new Map<string, { count: number; total: number }>();
  for (const c of contacts) {
    const entry = map.get(c.role) ?? { count: 0, total: 0 };
    entry.count += 1;
    entry.total += c.relevance;
    map.set(c.role, entry);
  }
  return Array.from(map.entries())
    .map(([role, { count, total }]) => ({ role, count, avgRelevance: Math.round(total / count) }))
    .sort((a, b) => b.count - a.count || b.avgRelevance - a.avgRelevance)
    .slice(0, limit);
}

/** Group recommendations by company (primary = highest relevance) (§21). */
export function groupByCompany(contacts: ContactRecommendation[]): CompanyContactGroup[] {
  const map = new Map<string, ContactRecommendation[]>();
  for (const c of contacts) {
    const arr = map.get(c.company);
    if (arr) arr.push(c);
    else map.set(c.company, [c]);
  }
  return Array.from(map.entries())
    .map(([company, recs]) => ({
      company,
      industry: recs[0].industry,
      recommendations: [...recs].sort((a, b) => b.relevance - a.relevance),
    }))
    .sort((a, b) => b.recommendations[0].relevance - a.recommendations[0].relevance);
}

export const PRIORITIES: LeadPriority[] = ['HOT', 'WARM', 'NURTURE', 'LOW'];
