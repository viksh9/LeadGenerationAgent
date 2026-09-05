import type { LeadPriority, LeadStatus, SignalType } from './lead';
import type { OpportunityType, StaffingNeed, Urgency } from './opportunity';

/**
 * Contact intelligence is Phase-1 ROLE intelligence, not verified people. The
 * backend persists a recommended decision-maker role (poc_title); a person is
 * only ever named when poc_name is actually present (currently never). Nothing
 * about a person is fabricated.
 */

export type DecisionMakerType = 'TECHNICAL' | 'BUSINESS' | 'DELIVERY' | 'PROCUREMENT' | 'VENDOR' | 'HR';

/** Where the recommendation came from (Phase 1: derived from lead intelligence). */
export type ContactSource = 'LEAD_INTELLIGENCE';

export type ContactConfidence = 'HIGH' | 'MEDIUM' | 'LOW';

/** Reuses the related lead's lifecycle status (no separate contact lifecycle). */
export type ContactStatus = LeadStatus;

export interface ContactRecommendation {
  /** Stable client key (leadId + role) — no fabricated backend contact id. */
  id: string;
  leadId: number;
  company: string;
  industry: string | null;
  location: string | null;

  role: string;
  personName: string | null; // poc_name — usually null (role, not person)
  linkedinUrl: string | null;
  publicContact: string | null;

  decisionMakerType: DecisionMakerType;
  relevance: number; // Phase-1 proxy = related lead score
  confidence: ContactConfidence; // band of relevance
  reason: string | null; // POC engine reason (not persisted -> null)
  recommendedAction: string | null;

  // Opportunity context (why the role matters)
  opportunityType: OpportunityType;
  opportunitySummary: string | null;
  staffingNeed: StaffingNeed;
  urgency: Urgency;
  urgencyReason: string | null;
  estimatedHiring: number | null;
  leadScore: number;
  priority: LeadPriority;
  status: ContactStatus;

  // Evidence
  signalType: SignalType | null;
  signalTitle: string | null;
  signalDate: string | null;
  sourceName: string | null;
  sourceUrl: string | null;
  signalConfidence: number | null;
  updatedAt: string | null;

  source: ContactSource;
}

export interface ContactSummary {
  total: number;
  highRelevance: number;
  technical: number;
  procurementVendor: number;
}

export interface TopTargetRole {
  role: string;
  count: number;
  avgRelevance: number;
}

export interface CompanyContactGroup {
  company: string;
  industry: string | null;
  recommendations: ContactRecommendation[];
}

export type ContactSortBy = 'relevance' | 'company' | 'lead_score' | 'priority' | 'updated';

export interface ContactFilterState {
  search: string;
  type: DecisionMakerType | '';
  role: string;
  priority: LeadPriority | '';
  industry: string;
  opportunityType: OpportunityType | '';
  confidence: ContactConfidence | '';
  minRelevance: string;
}
