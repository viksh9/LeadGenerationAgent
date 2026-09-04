import type { LeadPriority } from './lead';

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
