import type { LeadPriority, LeadStatus, SignalType } from './lead';

/**
 * Opportunity types. In Phase 1 these are DERIVED from the persisted lead
 * signal_type + hiring size (see services/opportunities.ts). When the backend
 * persists opportunity_analysis.opportunity_type, the adapter swaps to it and
 * this enum stays the same.
 */
export type OpportunityType =
  | 'NORMAL_HIRING'
  | 'PROJECT_DRIVEN_HIRING'
  | 'LARGE_SCALE_RAMP_UP'
  | 'STAFF_AUGMENTATION'
  | 'VENDOR_OPPORTUNITY'
  | 'TECHNOLOGY_IMPLEMENTATION'
  | 'DIGITAL_TRANSFORMATION'
  | 'LOW_CONFIDENCE';

export type StaffingNeed = 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN';
export type Urgency = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN';

/**
 * A qualified opportunity derived from a single lead. Every field maps to a
 * persisted Lead field or a documented deterministic derivation — nothing is
 * fabricated. `confidence` (opportunity confidence) is not persisted, so it is
 * always null (shown as "Not available").
 */
export interface Opportunity {
  leadId: number;
  company: string;
  industry: string | null;
  opportunityType: OpportunityType;
  businessReason: string | null;
  staffingNeed: StaffingNeed;
  estimatedHiring: number | null;
  urgency: Urgency;
  urgencyReason: string | null;
  technologies: string[];
  score: number;
  priority: LeadPriority;
  status: LeadStatus;
  confidence: number | null; // opportunity confidence — not persisted (null)
  signalConfidence: number | null;
  pocRole: string | null;
  pocName: string | null;
  pocLinkedin: string | null;
  recommendedAction: string | null;
  signalType: SignalType | null;
  signalTitle: string | null;
  signalDate: string | null;
  sourceName: string | null;
  sourceUrl: string | null;
  createdAt: string | null;
}

/** Funnel metrics across a set of opportunities. */
export interface OpportunitySummary {
  total: number;
  hot: number;
  highStaffing: number;
  highUrgency: number;
  qualified: number;
}

/** One bar/slice of the opportunity-type distribution chart. */
export interface OpportunityTypeDatum {
  type: OpportunityType;
  label: string;
  count: number;
}

export type OpportunitySortBy = 'score' | 'urgency' | 'team' | 'signal_date' | 'created';

/** Client-side filter set (synced to the URL). */
export interface OpportunityFilterState {
  search: string;
  type: OpportunityType | '';
  priority: LeadPriority | '';
  staffing: StaffingNeed | '';
  urgency: Urgency | '';
  industry: string;
  technology: string;
  status: LeadStatus | '';
}
