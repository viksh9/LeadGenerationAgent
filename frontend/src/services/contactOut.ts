import { api } from './api';

/**
 * ContactOut POC discovery/enrichment API client.
 *
 * Real data only: a `POC` is shown as a real person ONLY when ContactOut returned
 * and validated them; otherwise the UI shows role-only recommendations. Contact
 * fields are the actual returned values or empty — never fabricated. The API token
 * is never exposed by any of these endpoints.
 */

export type ContactTrustStatus = 'VERIFIED' | 'LIKELY' | 'UNVERIFIED' | 'NO_CONTACT_DATA';
export type ContactOutConfigStatus = 'CONFIGURED' | 'NOT_CONFIGURED' | 'DISABLED';
export type ContactOutConnectionStatus =
  | 'CONNECTED'
  | 'AUTHENTICATION_FAILED'
  | 'RATE_LIMITED'
  | 'NOT_CONFIGURED'
  | 'UNAVAILABLE'
  | 'DEGRADED'
  | 'RESTRICTED';
export type DiscoveryStatus =
  | 'ENRICHED'
  | 'CACHED'
  | 'NO_POC_FOUND'
  | 'NOT_CONFIGURED'
  | 'RATE_LIMITED'
  | 'UNAVAILABLE';

export interface POC {
  id: number;
  company_id: number | null;
  company_name: string | null;
  full_name: string | null;
  job_title: string | null;
  seniority: string | null;
  company_domain: string | null;
  professional_network_url: string | null;
  business_email: string | null;
  business_phone: string | null;
  email_status: string | null;
  contact_source: string | null;
  source_url: string | null;
  match_score: number;
  contact_trust_score: number;
  contact_trust_status: ContactTrustStatus | null;
  is_current: boolean;
  verification_status: string;
  last_verified_at: string | null;
}

export interface RecommendedRole {
  role: string;
  role_category: string;
  decision_maker_type: string;
  relevance_score: number;
  reason: string;
  is_primary: boolean;
}

export interface POCList {
  lead_id: number;
  company_name: string | null;
  contactout_status: ContactOutConfigStatus;
  pocs: POC[];
  recommended_roles: RecommendedRole[];
  recommendation_confidence: number;
  note: string | null;
}

export interface POCDiscovery {
  lead_id: number | null;
  company_id: number | null;
  company_name: string | null;
  status: DiscoveryStatus;
  candidates_found: number;
  searches_used: number;
  enrichments_used: number;
  persisted: number;
  reason: string;
  error_code: string | null;
  pocs: POC[];
}

export interface ContactOutStatus {
  status: ContactOutConfigStatus;
  configured: boolean;
  note: string;
  people_search_rate_per_minute: number;
  other_rate_per_minute: number;
  max_poc_searches_per_opportunity: number;
  max_enrichments_per_opportunity: number;
  cache_ttl_hours: number;
}

export interface ConnectionTestResult {
  source_id: string;
  connection_status: ContactOutConnectionStatus;
  message: string | null;
  performed_request: boolean;
  checked_at: string;
}

export async function fetchLeadPocs(leadId: number, signal?: AbortSignal): Promise<POCList> {
  const { data } = await api.get<POCList>(`/leads/${leadId}/pocs`, { signal });
  return data;
}

export async function discoverLeadPocs(leadId: number, force = false): Promise<POCDiscovery> {
  const { data } = await api.post<POCDiscovery>(`/leads/${leadId}/pocs/discover`, null, {
    params: { force },
  });
  return data;
}

export async function enrichPoc(pocId: number): Promise<POCDiscovery> {
  const { data } = await api.post<POCDiscovery>(`/pocs/${pocId}/enrich`);
  return data;
}

export async function fetchContactOutStatus(signal?: AbortSignal): Promise<ContactOutStatus> {
  const { data } = await api.get<ContactOutStatus>('/integrations/contactout/status', { signal });
  return data;
}

export async function testContactOut(): Promise<ConnectionTestResult> {
  const { data } = await api.post<ConnectionTestResult>('/integrations/contactout/test');
  return data;
}

// --- display helpers (label + Tailwind classes; colour + value, never colour alone) ---
export interface BadgeDisplay {
  label: string;
  className: string;
}

const EMERALD = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
const BLUE = 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300';
const AMBER = 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300';
const SLATE = 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';
const ROSE = 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300';

const TRUST: Record<ContactTrustStatus, BadgeDisplay> = {
  VERIFIED: { label: 'Verified', className: EMERALD },
  LIKELY: { label: 'Likely', className: BLUE },
  UNVERIFIED: { label: 'Unverified', className: AMBER },
  NO_CONTACT_DATA: { label: 'No contact data', className: SLATE },
};

export function contactTrustDisplay(status: ContactTrustStatus | null): BadgeDisplay {
  return (status && TRUST[status]) || { label: 'Unknown', className: SLATE };
}

const CONFIG_STATUS: Record<string, BadgeDisplay> = {
  CONFIGURED: { label: 'Configured', className: BLUE },
  NOT_CONFIGURED: { label: 'Not configured', className: SLATE },
  DISABLED: { label: 'Disabled', className: SLATE },
  CONNECTED: { label: 'Connected', className: EMERALD },
  AUTHENTICATION_FAILED: { label: 'Authentication failed', className: ROSE },
  RATE_LIMITED: { label: 'Rate limited', className: AMBER },
  UNAVAILABLE: { label: 'Unavailable', className: ROSE },
  DEGRADED: { label: 'Degraded', className: AMBER },
  RESTRICTED: { label: 'Restricted', className: AMBER },
};

export function contactOutStatusDisplay(status: string): BadgeDisplay {
  return CONFIG_STATUS[status] ?? { label: status, className: SLATE };
}
