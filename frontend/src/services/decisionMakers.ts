import { api } from './api';

/**
 * Real decision-maker / contact + stakeholder data from the backend.
 *
 * The distinction is mandatory and load-bearing across the UI:
 *   - a recommended ROLE (StakeholderRole) is NOT a person;
 *   - a person (DecisionMaker with a full_name) is NOT necessarily a verified
 *     contact — check verification_status.
 *
 * Nullable fields stay nullable so the UI renders honest "not available" states
 * and never fabricates a person, email, or URL.
 */
export interface DecisionMaker {
  id: string;
  company_id: number | null;
  company_name: string | null;
  full_name: string | null;
  job_title: string | null;
  normalized_role: string | null;
  role_category: string;
  department: string | null;
  seniority: string | null;
  profile_url: string | null;
  professional_network_url: string | null;
  business_email: string | null;
  business_phone: string | null;
  contact_type: string;
  email_status: string | null;
  contact_source: string | null;
  source_type: string | null;
  source_url: string | null;
  identity_confidence: number;
  role_confidence: number;
  company_confidence: number;
  contact_confidence: number;
  evidence_confidence: number;
  freshness_score: number;
  verification_status: VerificationStatus;
  match_status: string | null;
  data_provenance: string;
  last_verified_at: string | null;
}

export type VerificationStatus =
  | 'VERIFIED'
  | 'PARTIALLY_VERIFIED'
  | 'UNVERIFIED'
  | 'STALE'
  | 'CONTRADICTED';

export interface DecisionMakerList {
  items: DecisionMaker[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface StakeholderRole {
  role: string;
  role_category: string;
  decision_maker_type: string;
  relevance_score: number;
  reason: string | null;
  is_primary: boolean;
}

export type OutreachReadiness = 'READY' | 'ROLE_ONLY' | 'RESEARCH_REQUIRED' | 'HOLD';

export interface LeadStakeholders {
  lead_id: number;
  company_name: string | null;
  recommended_roles: StakeholderRole[];
  recommendation_confidence: number;
  verified_decision_makers: DecisionMaker[];
  business_contacts: DecisionMaker[];
  outreach_readiness: OutreachReadiness;
  outreach_reasons: string[];
}

export interface ContactsParams {
  page?: number;
  page_size?: number;
  company?: string;
  role_category?: string;
  verification_status?: string;
  /** false -> include business contacts (contact-only rows), not just people. */
  people_only?: boolean;
}

/** Paginated real decision-makers / contacts (GET /contacts). */
export async function fetchContacts(
  params: ContactsParams = {},
  signal?: AbortSignal,
): Promise<DecisionMakerList> {
  const { data } = await api.get<DecisionMakerList>('/contacts', { params, signal });
  return data;
}

/** A single decision-maker / contact (GET /contacts/{id}). */
export async function fetchContact(id: string, signal?: AbortSignal): Promise<DecisionMaker> {
  const { data } = await api.get<DecisionMaker>(`/contacts/${id}`, { signal });
  return data;
}

/** Stakeholder recommendation + verified people/contacts for a lead. */
export async function fetchLeadStakeholders(
  leadId: number,
  signal?: AbortSignal,
): Promise<LeadStakeholders> {
  const { data } = await api.get<LeadStakeholders>(`/leads/${leadId}/stakeholders`, { signal });
  return data;
}

export interface BadgeDisplay {
  label: string;
  className: string;
}

const EMERALD = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
const BLUE = 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300';
const AMBER = 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300';
const ROSE = 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300';
const SLATE = 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';

const VERIFICATION_DISPLAY: Record<VerificationStatus, BadgeDisplay> = {
  VERIFIED: { label: 'Verified', className: EMERALD },
  PARTIALLY_VERIFIED: { label: 'Partially verified', className: BLUE },
  UNVERIFIED: { label: 'Unverified', className: SLATE },
  STALE: { label: 'Stale', className: AMBER },
  CONTRADICTED: { label: 'Contradicted', className: ROSE },
};

/** Display label + honest Tailwind badge classes for a verification status. */
export function verificationDisplay(status: string): BadgeDisplay {
  return VERIFICATION_DISPLAY[status as VerificationStatus] ?? { label: status, className: SLATE };
}

const READINESS_DISPLAY: Record<OutreachReadiness, BadgeDisplay> = {
  READY: { label: 'Ready', className: EMERALD },
  ROLE_ONLY: { label: 'Role only', className: BLUE },
  RESEARCH_REQUIRED: { label: 'Research required', className: AMBER },
  HOLD: { label: 'Hold', className: ROSE },
};

/** Display label + honest Tailwind badge classes for an outreach-readiness band. */
export function outreachReadinessDisplay(r: string): BadgeDisplay {
  return READINESS_DISPLAY[r as OutreachReadiness] ?? { label: r, className: SLATE };
}
