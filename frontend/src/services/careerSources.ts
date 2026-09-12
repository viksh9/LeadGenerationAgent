import { api } from './api';

/**
 * Applicant-tracking provider behind a company's official careers presence.
 * These are direct, first-party sources (TIER_1) — not job aggregators.
 */
export type AtsProvider = 'GREENHOUSE' | 'LEVER' | 'CAREER_PAGE' | 'OTHER';

/**
 * Real career-source lifecycle states from the backend (GET /career-sources).
 * A source is only CONNECTED after a verified live check — never green merely
 * because a record exists.
 */
export type CareerSourceStatus =
  | 'DISCOVERY_REQUIRED'
  | 'CONFIGURED'
  | 'CONNECTED'
  | 'DISABLED'
  | 'ERROR';

/** A discovered/configured official career source for a company. */
export interface CareerSource {
  id: number;
  company_id: number | null;
  company_name: string | null;
  ats_provider: AtsProvider;
  board_identifier: string | null;
  careers_url: string | null;
  discovery_method: string | null;
  status: CareerSourceStatus;
  enabled: boolean;
  evidence_tier: string;
  last_checked_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface CareerSourceList {
  items: CareerSource[];
  total: number;
}

/** Official career sources registry (GET /career-sources). */
export async function fetchCareerSources(): Promise<CareerSourceList> {
  const { data } = await api.get<CareerSourceList>('/career-sources');
  return data;
}

/** Inputs for an ad-hoc, live discovery (POST /career-sources/discover). */
export interface DiscoverByDomainBody {
  company_name: string;
  domain?: string;
  careers_url?: string;
}

/**
 * Real result of a live, SSRF-safe discovery against a supplied domain / careers
 * URL. `found` is true only when a real Greenhouse/Lever board id was detected;
 * `verified` is true only when ownership was confirmed. Nothing is fabricated and
 * nothing is persisted (no stored Company entity is involved).
 */
export interface DiscoverResult {
  company_id: number | null;
  company_name: string | null;
  found: boolean;
  verified: boolean;
  provider: AtsProvider | null;
  board_identifier: string | null;
  careers_url: string | null;
  discovery_method: string | null;
  detail: string;
}

/** Run a live ATS/career-source discovery for a provided company + domain/URL. */
export async function discoverCareerSourceByDomain(
  body: DiscoverByDomainBody,
): Promise<DiscoverResult> {
  const payload = {
    company_name: body.company_name.trim(),
    domain: body.domain?.trim() || undefined,
    careers_url: body.careers_url?.trim() || undefined,
  };
  const { data } = await api.post<DiscoverResult>('/career-sources/discover', payload);
  return data;
}

/** Display label + honest Tailwind badge classes for a career-source status. */
export interface CareerSourceStatusDisplay {
  label: string;
  className: string;
}

const EMERALD = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
const BLUE = 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300';
const AMBER = 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300';
const SLATE = 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';
const ROSE = 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300';

const STATUS_DISPLAY: Record<CareerSourceStatus, CareerSourceStatusDisplay> = {
  CONNECTED: { label: 'Connected', className: EMERALD },
  CONFIGURED: { label: 'Configured', className: BLUE },
  DISCOVERY_REQUIRED: { label: 'Discovery required', className: AMBER },
  DISABLED: { label: 'Disabled', className: SLATE },
  ERROR: { label: 'Error', className: ROSE },
};

export function careerStatusDisplay(status: CareerSourceStatus): CareerSourceStatusDisplay {
  return STATUS_DISPLAY[status] ?? { label: status, className: SLATE };
}

const PROVIDER_LABEL: Record<AtsProvider, string> = {
  GREENHOUSE: 'Greenhouse',
  LEVER: 'Lever',
  CAREER_PAGE: 'Official career page',
  OTHER: 'Other',
};

export function providerLabel(provider: AtsProvider): string {
  return PROVIDER_LABEL[provider] ?? 'Other';
}

/**
 * Provenance of a job/evidence source by its name. Direct first-party sources
 * (an ATS or a company career page) are distinguished from third-party job
 * aggregators, so the UI never conflates the two.
 */
export type SourceKind = 'official' | 'aggregator' | 'other';

export function sourceKind(sourceName: string | null | undefined): SourceKind {
  if (!sourceName) return 'other';
  const s = sourceName.toLowerCase();
  if (/greenhouse|lever|company_career|career_page|careers?_page|company career/.test(s)) {
    return 'official';
  }
  if (/adzuna|jooble/.test(s)) return 'aggregator';
  return 'other';
}

export interface SourceKindDisplay {
  label: string;
  className: string;
}

const SOURCE_KIND_DISPLAY: Record<SourceKind, SourceKindDisplay | null> = {
  official: { label: 'Direct official', className: EMERALD },
  aggregator: { label: 'Aggregator', className: AMBER },
  other: null,
};

/** Chip label + classes for a source kind, or null when there's nothing honest to say. */
export function sourceKindDisplay(kind: SourceKind): SourceKindDisplay | null {
  return SOURCE_KIND_DISPLAY[kind];
}
