import { api } from '@/services/api';

/** Multi-provider contact-enrichment provider status + connectivity test (Prompt 49). */

export type ProviderConfigStatus = 'CONFIGURED' | 'NOT_CONFIGURED' | 'DISABLED';

export type ProviderTestResult =
  | 'LIVE_VERIFIED'
  | 'NOT_CONFIGURED'
  | 'AUTHENTICATION_FAILED'
  | 'FORBIDDEN'
  | 'RATE_LIMITED'
  | 'SOURCE_UNAVAILABLE'
  | 'ERROR';

export interface ProviderCapabilities {
  person_search?: boolean;
  person_enrichment?: boolean;
  company_enrichment?: boolean;
  email_finder?: boolean;
  email_verification?: boolean;
  decision_maker_search?: boolean;
}

export interface EnrichmentProviderStatus {
  provider: string;
  status: ProviderConfigStatus;
  capabilities: ProviderCapabilities;
}

export interface EnrichmentStatus {
  providers: EnrichmentProviderStatus[];
}

export interface ProviderTestResponse {
  provider: string;
  result: ProviderTestResult;
  message: string | null;
  performed_request: boolean;
  checked_at: string;
}

export async function fetchEnrichmentStatus(signal?: AbortSignal): Promise<EnrichmentStatus> {
  const { data } = await api.get<EnrichmentStatus>('/integrations/enrichment/status', { signal });
  return data;
}

export async function testEnrichmentProvider(provider: string): Promise<ProviderTestResponse> {
  const { data } = await api.post<ProviderTestResponse>(`/integrations/${provider}/test`);
  return data;
}

const PROVIDER_LABELS: Record<string, string> = {
  contactout: 'ContactOut',
  apollo: 'Apollo',
  lusha: 'Lusha',
  prospeo: 'Prospeo',
  hunter: 'Hunter',
};

export function providerLabel(name: string): string {
  return PROVIDER_LABELS[name] ?? name;
}

const CAPABILITY_LABELS: Record<keyof ProviderCapabilities, string> = {
  person_search: 'People search',
  person_enrichment: 'Person enrichment',
  company_enrichment: 'Company enrichment',
  email_finder: 'Email finder',
  email_verification: 'Email verification',
  decision_maker_search: 'Decision-maker search',
};

export function capabilityLabels(caps: ProviderCapabilities): string[] {
  return (Object.keys(CAPABILITY_LABELS) as (keyof ProviderCapabilities)[])
    .filter((k) => caps[k])
    .map((k) => CAPABILITY_LABELS[k]);
}

const EMERALD = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
const AMBER = 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300';
const ROSE = 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300';
const SLATE = 'bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300';

export function configStatusDisplay(status: ProviderConfigStatus): { label: string; className: string } {
  if (status === 'CONFIGURED') return { label: 'Configured', className: EMERALD };
  if (status === 'DISABLED') return { label: 'Disabled', className: SLATE };
  return { label: 'Not configured', className: AMBER };
}

export function testResultDisplay(result: ProviderTestResult): { label: string; className: string } {
  switch (result) {
    case 'LIVE_VERIFIED':
      return { label: 'Live verified', className: EMERALD };
    case 'NOT_CONFIGURED':
      return { label: 'Not configured', className: AMBER };
    case 'RATE_LIMITED':
      return { label: 'Rate limited', className: AMBER };
    case 'AUTHENTICATION_FAILED':
      return { label: 'Auth failed', className: ROSE };
    case 'FORBIDDEN':
      return { label: 'Forbidden', className: ROSE };
    case 'SOURCE_UNAVAILABLE':
      return { label: 'Unavailable', className: ROSE };
    default:
      return { label: 'Error', className: ROSE };
  }
}
