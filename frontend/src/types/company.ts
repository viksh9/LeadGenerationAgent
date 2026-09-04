import type { Lead, LeadPriority } from './lead';

/**
 * A company summary derived from leads. The backend has no company entity, so
 * these are aggregated client-side by company_name.
 */
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
}

export type CompanySortBy = 'score' | 'name' | 'leads';

/** A decision-maker / point of contact surfaced across a company's leads. */
export interface CompanyContact {
  name: string;
  title: string | null;
  linkedinUrl: string | null;
}

/**
 * The full profile for one company: the summary fields plus the underlying
 * leads (each a signal) and de-duplicated contacts. Aggregated client-side.
 */
export interface CompanyDetail extends CompanySummary {
  priorityCounts: Record<LeadPriority, number>;
  leads: Lead[];
  contacts: CompanyContact[];
}
