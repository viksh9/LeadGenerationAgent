import type { Lead, LeadPriority, LeadStatus, SignalType } from './lead';

/**
 * Company intelligence is derived client-side from Lead data. The backend has no
 * company entity, so companies are grouped by company_name (a temporary Phase
 * 1/2 identifier — see companyIntelligence.ts). Every type here maps to fields
 * that actually exist on a Lead; nothing is fabricated.
 */

/** A company summary + list-level metrics, aggregated from its leads. */
export interface CompanySummary {
  name: string;
  industry: string | null;
  location: string | null;
  companySize: string | null;
  website: string | null;
  leadCount: number;
  bestScore: number;
  topPriority: LeadPriority;
  technologies: string[];
  estimatedHiring: number;
  latestSignal: string | null;
  totalSignals: number;
  latestSignalType: SignalType | null;
}

export type CompanySortBy = 'score' | 'name' | 'leads';

/** Account-level metrics derivable from the company's leads. */
export interface CompanyMetrics {
  totalLeads: number;
  hotLeads: number;
  warmLeads: number;
  totalSignals: number;
  latestSignalDate: string | null;
  highestLeadScore: number;
  technologyCount: number;
  opportunityCount: number;
}

/** A technology with how many of the company's leads reference it. */
export interface CompanyTechnology {
  name: string;
  leadCount: number;
}

/** One business signal (one per lead) for the timeline. */
export interface CompanySignal {
  leadId: number;
  signalType: SignalType | null;
  title: string | null;
  description: string | null;
  date: string | null;
  confidence: number | null;
  score: number;
}

/** An opportunity derived from a lead (structured staffing/urgency not stored). */
export interface CompanyOpportunity {
  leadId: number;
  summary: string | null;
  estimatedHiring: number | null;
  score: number;
  priority: LeadPriority;
  status: LeadStatus;
}

/** A project referenced by a lead. */
export interface CompanyProject {
  leadId: number;
  name: string;
  value: number | null;
  date: string | null;
  signalType: SignalType | null;
  opportunitySummary: string | null;
}

/**
 * A recommended decision-maker ROLE aggregated across leads. A person is only
 * named when a lead actually provides poc_name — never invented.
 */
export interface DecisionMakerRecommendation {
  role: string;
  name: string | null;
  linkedinUrl: string | null;
  leadCount: number;
}

/** A source/evidence record from a single lead. */
export interface CompanyEvidenceItem {
  leadId: number;
  sourceName: string | null;
  sourceUrl: string | null;
  signalDate: string | null;
  lastVerified: string | null;
  confidence: number | null;
}

/** Aggregated hiring signal across the company's leads. */
export interface CompanyHiring {
  estimatedHiring: number;
  maxEstimatedHiring: number;
  roles: string[];
  technologies: string[];
}

export interface CompanyContact {
  name: string;
  title: string | null;
  linkedinUrl: string | null;
}

/** The full derived intelligence profile for one company. */
export interface CompanyIntelligence extends CompanySummary {
  metrics: CompanyMetrics;
  technologies: string[]; // union (kept for back-compat with summary)
  technologyLandscape: CompanyTechnology[]; // with frequency, sorted desc
  signals: CompanySignal[]; // timeline, newest first
  opportunities: CompanyOpportunity[];
  projects: CompanyProject[];
  decisionMakers: DecisionMakerRecommendation[];
  evidence: CompanyEvidenceItem[];
  hiring: CompanyHiring;
  recommendedAction: string;
  contacts: CompanyContact[];
  leads: Lead[]; // all matched leads (for related-leads views)
}
