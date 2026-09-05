import type { Lead, LeadPriority } from '@/types/lead';
import type {
  MessageStrategy,
  OutreachFilterState,
  OutreachItem,
  OutreachSortBy,
  OutreachStatus,
  OutreachSummary,
} from '@/types/outreach';
import type { OpportunityType } from '@/types/opportunity';
import { deriveOpportunityType, deriveStaffingNeed, deriveUrgency } from '@/services/opportunities';

/**
 * Outreach adapter. TEMPORARY STRATEGY (Phase 1): no backend Outreach entity.
 * Items are derived from leads with a persisted `recommended_pitch`. See
 * docs/frontend-outreach.md. All derivation/parsing/filtering/sorting live here.
 */

const PRIORITY_RANK: Record<LeadPriority, number> = { HOT: 3, WARM: 2, NURTURE: 1, LOW: 0 };

export const OUTREACH_STATUS_LABELS: Record<OutreachStatus, string> = {
  DRAFT: 'Draft',
  READY: 'Ready',
  REVIEWED: 'Reviewed',
  CONTACTED: 'Contacted',
  RESPONDED: 'Responded',
  MEETING: 'Meeting',
  FOLLOW_UP: 'Follow up',
  COMPLETED: 'Completed',
};

export const OUTREACH_STATUSES = Object.keys(OUTREACH_STATUS_LABELS) as OutreachStatus[];

export const MESSAGE_STRATEGY_LABELS: Record<MessageStrategy, string> = {
  PROJECT_RAMP_UP: 'Project Ramp-Up',
  STAFF_AUGMENTATION: 'Staff Augmentation',
  VENDOR_OPPORTUNITY: 'Vendor Opportunity',
  DIGITAL_TRANSFORMATION: 'Digital Transformation',
  TECHNOLOGY_IMPLEMENTATION: 'Technology Implementation',
  NORMAL_HIRING: 'Normal Hiring',
  NURTURE: 'Nurture',
};

const IN_PROGRESS: OutreachStatus[] = ['CONTACTED', 'RESPONDED', 'MEETING', 'FOLLOW_UP'];

/** Split a pitch into an optional subject line and the remaining body. */
export function parsePitch(pitch: string): { subject: string | null; body: string } {
  const text = pitch.trim();
  const match = text.match(/^\s*subject:\s*(.+?)\s*(?:\n|$)/i);
  if (!match) return { subject: null, body: text };
  return { subject: match[1].trim(), body: text.slice(match[0].length).trim() || text };
}

/** Message strategy derived from the (derived) opportunity type. */
export function deriveMessageStrategy(type: OpportunityType): MessageStrategy {
  switch (type) {
    case 'LARGE_SCALE_RAMP_UP':
    case 'PROJECT_DRIVEN_HIRING':
      return 'PROJECT_RAMP_UP';
    case 'STAFF_AUGMENTATION':
      return 'STAFF_AUGMENTATION';
    case 'VENDOR_OPPORTUNITY':
      return 'VENDOR_OPPORTUNITY';
    case 'DIGITAL_TRANSFORMATION':
      return 'DIGITAL_TRANSFORMATION';
    case 'TECHNOLOGY_IMPLEMENTATION':
      return 'TECHNOLOGY_IMPLEMENTATION';
    case 'NORMAL_HIRING':
      return 'NORMAL_HIRING';
    default:
      return 'NURTURE';
  }
}

/** Preparation status derived from the persisted lead status (frontend-only). */
export function deriveOutreachStatus(lead: Lead): OutreachStatus {
  switch (lead.status) {
    case 'NEW':
    case 'RESEARCHED':
      return lead.recommended_pitch ? 'READY' : 'DRAFT';
    case 'CONTACTED':
      return 'CONTACTED';
    case 'REPLIED':
      return 'RESPONDED';
    case 'MEETING':
      return 'MEETING';
    case 'QUALIFIED':
      return 'REVIEWED';
    case 'PROPOSAL':
      return 'FOLLOW_UP';
    case 'WON':
    case 'LOST':
      return 'COMPLETED';
    case 'NURTURE':
    default:
      return 'DRAFT';
  }
}

/** Reasons an item needs research before outreach (empty => ready) (§23). */
function reviewReasons(lead: Lead): string[] {
  const reasons: string[] = [];
  if (!lead.recommended_pitch) reasons.push('No pitch generated');
  if (!lead.poc_title) reasons.push('No target role identified');
  if (lead.lead_priority === 'LOW' || lead.lead_priority === 'NURTURE') reasons.push('Low priority');
  if (lead.signal_confidence != null && lead.signal_confidence < 50) reasons.push('Weak signal');
  if (!lead.opportunity_summary) reasons.push('Opportunity unclear');
  return reasons;
}

/** Ready for outreach: HOT/WARM + pitch + target role, and not low-signal (§22). */
function isReady(lead: Lead): boolean {
  return (
    (lead.lead_priority === 'HOT' || lead.lead_priority === 'WARM') &&
    Boolean(lead.recommended_pitch) &&
    Boolean(lead.poc_title) &&
    !(lead.signal_confidence != null && lead.signal_confidence < 50)
  );
}

/** Deterministic Lead -> Outreach mapping. `now` is injectable for testing. */
export function mapLeadToOutreach(lead: Lead, now: number = Date.now()): OutreachItem {
  const pitch = lead.recommended_pitch ?? '';
  const { subject, body } = pitch ? parsePitch(pitch) : { subject: null, body: '' };
  const opportunityType = deriveOpportunityType(lead);
  const { urgency, reason } = deriveUrgency(lead.signal_date, now);
  return {
    leadId: lead.id,
    company: lead.company_name,
    industry: lead.industry,
    role: lead.poc_title,
    message: {
      subject,
      body,
      pitch,
      linkedin: null, // not persisted
      talkingPoints: [], // not persisted
    },
    recommendedAction: lead.recommended_action,
    messageStrategy: deriveMessageStrategy(opportunityType),
    pitchConfidence: null, // not persisted
    opportunityType,
    opportunitySummary: lead.opportunity_summary,
    staffingNeed: deriveStaffingNeed(lead.estimated_hiring),
    urgency,
    urgencyReason: reason,
    estimatedHiring: lead.estimated_hiring,
    technologies: lead.technologies ?? [],
    priority: lead.lead_priority,
    score: lead.lead_score,
    status: deriveOutreachStatus(lead),
    leadStatus: lead.status,
    signalType: lead.signal_type,
    signalTitle: lead.signal_title,
    signalDate: lead.signal_date,
    sourceName: lead.source_name,
    sourceUrl: lead.source_url,
    signalConfidence: lead.signal_confidence,
    updatedAt: lead.updated_at,
    ready: isReady(lead),
    reviewReasons: reviewReasons(lead),
  };
}

export function mapLeadsToOutreach(leads: Lead[], now: number = Date.now()): OutreachItem[] {
  return leads.map((lead) => mapLeadToOutreach(lead, now));
}

/** Ready items first, then HOT>WARM>…, then score desc — the queue order (§5/§21). */
export function queueOrder(a: OutreachItem, b: OutreachItem): number {
  return (
    PRIORITY_RANK[b.priority] - PRIORITY_RANK[a.priority] || b.score - a.score
  );
}

export function splitQueue(items: OutreachItem[]): { ready: OutreachItem[]; needsReview: OutreachItem[] } {
  const ready = items.filter((i) => i.ready).sort(queueOrder);
  const needsReview = items.filter((i) => !i.ready).sort(queueOrder);
  return { ready, needsReview };
}

export function filterOutreach(items: OutreachItem[], f: OutreachFilterState): OutreachItem[] {
  const term = f.search.trim().toLowerCase();
  const role = f.role.trim().toLowerCase();
  const industry = f.industry.trim().toLowerCase();
  const min = f.minScore === '' ? null : Number(f.minScore);
  return items.filter((o) => {
    if (f.priority && o.priority !== f.priority) return false;
    if (f.opportunityType && o.opportunityType !== f.opportunityType) return false;
    if (f.status && o.status !== f.status) return false;
    if (min != null && Number.isFinite(min) && o.score < min) return false;
    if (role && !(o.role ?? '').toLowerCase().includes(role)) return false;
    if (industry && !(o.industry ?? '').toLowerCase().includes(industry)) return false;
    if (term) {
      const haystack = [
        o.company,
        o.role ?? '',
        o.message.subject ?? '',
        o.technologies.join(' '),
        o.signalTitle ?? '',
      ]
        .join(' ')
        .toLowerCase();
      if (!haystack.includes(term)) return false;
    }
    return true;
  });
}

export function sortOutreach(items: OutreachItem[], sortBy: OutreachSortBy): OutreachItem[] {
  const copy = [...items];
  switch (sortBy) {
    case 'score':
      return copy.sort((a, b) => b.score - a.score);
    case 'company':
      return copy.sort((a, b) => a.company.localeCompare(b.company) || b.score - a.score);
    case 'opportunity':
      return copy.sort((a, b) => a.opportunityType.localeCompare(b.opportunityType) || b.score - a.score);
    case 'signal_date':
      return copy.sort((a, b) => (b.signalDate ?? '').localeCompare(a.signalDate ?? ''));
    case 'created':
      return copy.sort((a, b) => (b.updatedAt ?? '').localeCompare(a.updatedAt ?? ''));
    case 'priority':
    default:
      return copy.sort(queueOrder);
  }
}

export function buildOutreachSummary(items: OutreachItem[]): OutreachSummary {
  return {
    ready: items.filter((i) => i.ready).length,
    needsReview: items.filter((i) => !i.ready).length,
    hot: items.filter((i) => i.priority === 'HOT').length,
    inProgress: items.filter((i) => IN_PROGRESS.includes(i.status)).length,
  };
}

export const PRIORITIES: LeadPriority[] = ['HOT', 'WARM', 'NURTURE', 'LOW'];
