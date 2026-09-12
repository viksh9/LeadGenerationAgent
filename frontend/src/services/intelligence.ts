import { api } from '@/services/api';
import type { POC, RecommendedRole } from '@/services/contactOut';

/** Lead Intelligence aggregation (Prompt 50). Read-model over existing engines —
 *  every value is source-backed; nothing is fabricated. */

export type PocStatus =
  | 'VERIFIED'
  | 'LIKELY'
  | 'RECOMMENDED_ROLE_ONLY'
  | 'STALE'
  | 'FORMER'
  | 'UNVERIFIED';

export type HighlightTrust = 'HIGH' | 'MEDIUM' | 'LOW';
export type FreshnessStatus = 'FRESH' | 'AGING' | 'STALE' | 'UNKNOWN';

export interface SourceRef {
  field: string;
  value: string | null;
  source: string;
  source_type: string | null;
  source_url: string | null;
  source_record_id: string | null;
  trust_score: number;
  verification_status: string | null;
  evidence: string | null;
  retrieved_at: string | null;
  last_verified_at: string | null;
}

export interface ProfileHighlight {
  highlight_title: string;
  highlight_text: string;
  trust_level: HighlightTrust;
  supporting_signal_ids: number[];
  supporting_source_ids: string[];
  ai_generated: boolean;
}

export interface ProfileHighlights {
  highlights: ProfileHighlight[];
  ai_available: boolean;
  ai_insight: string | null;
  model_version: string | null;
  generated_at: string | null;
}

export interface CompanyProfile {
  company_name: string | null;
  industry: string | null;
  india_presence: string;
  india_entity_type: string | null;
  website: string | null;
  primary_location: string | null;
  registered_location: string | null;
  career_site: string | null;
  technology_focus: string[];
  current_hiring_signal: string | null;
  opportunity: string | null;
  data_trust: number;
  headline: string;
}

export interface OpportunityViewData {
  opportunity_type: string;
  label: string;
  staffing_need: string;
  estimated_team: number | null;
  urgency: string;
  technologies: string[];
  signals: string[];
}

export interface POCIntelligence {
  poc: POC;
  poc_status: PocStatus;
  role_match_score: number;
  contact_trust_score: number;
  contact_trust_status: string | null;
  is_primary: boolean;
}

export interface LeadIntelligence {
  lead_id: number;
  company_id: number | null;
  company_name: string | null;
  lead_score: number;
  lead_priority: string | null;
  data_trust: number;
  contact_trust: number;
  signal_summary: string;
  company_profile: CompanyProfile;
  opportunity: OpportunityViewData;
  recommended_roles: RecommendedRole[];
  recommendation_confidence: number;
  primary_poc: POCIntelligence | null;
  secondary_pocs: POCIntelligence[];
  ai_highlights: ProfileHighlights;
  sources: SourceRef[];
  freshness_score: number;
  freshness_status: FreshnessStatus;
  sales_action: string;
  generated_at: string | null;
}

export interface LeadSources {
  lead_id: number;
  company_id: number | null;
  company_name: string | null;
  sources: SourceRef[];
}

export async function fetchLeadIntelligence(leadId: number, signal?: AbortSignal): Promise<LeadIntelligence> {
  const { data } = await api.get<LeadIntelligence>(`/leads/${leadId}/intelligence`, { signal });
  return data;
}

export async function fetchLeadSources(leadId: number, signal?: AbortSignal): Promise<LeadSources> {
  const { data } = await api.get<LeadSources>(`/leads/${leadId}/sources`, { signal });
  return data;
}

export async function refreshLeadIntelligence(leadId: number): Promise<LeadIntelligence> {
  const { data } = await api.post<LeadIntelligence>(`/leads/${leadId}/intelligence/refresh`);
  return data;
}

// --- Display helpers (label + className together, never color alone) --------- //
const EMERALD = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
const BLUE = 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300';
const AMBER = 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300';
const SLATE = 'bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300';
const ROSE = 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300';

export function pocStatusDisplay(status: PocStatus): { label: string; className: string } {
  switch (status) {
    case 'VERIFIED':
      return { label: 'Verified', className: EMERALD };
    case 'LIKELY':
      return { label: 'Likely', className: BLUE };
    case 'STALE':
      return { label: 'Stale', className: AMBER };
    case 'FORMER':
      return { label: 'Former', className: SLATE };
    case 'RECOMMENDED_ROLE_ONLY':
      return { label: 'Recommended role only', className: SLATE };
    default:
      return { label: 'Unverified', className: AMBER };
  }
}

export function trustLevelDisplay(level: HighlightTrust): { label: string; className: string } {
  if (level === 'HIGH') return { label: 'High', className: EMERALD };
  if (level === 'MEDIUM') return { label: 'Medium', className: BLUE };
  return { label: 'Low', className: AMBER };
}

export function freshnessDisplay(status: FreshnessStatus): { label: string; className: string } {
  if (status === 'FRESH') return { label: 'Fresh', className: EMERALD };
  if (status === 'AGING') return { label: 'Aging', className: AMBER };
  if (status === 'STALE') return { label: 'Stale', className: ROSE };
  return { label: 'Unknown', className: SLATE };
}
