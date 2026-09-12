import { api } from './api';
import type { POC } from './contactOut';

/**
 * Free/public intelligence API client (official company website, GitHub, Wikidata).
 * Real data only — the server returns real people/facts or nothing; never fabricated.
 */

export interface PublicIntelligenceDiscovery {
  lead_id: number | null;
  company_id: number | null;
  company_name: string | null;
  status: 'ENRICHED' | 'CACHED' | 'NO_POC_FOUND' | 'DISABLED';
  people_found: number;
  persisted: number;
  provider_status: Record<string, string>;
  company_facts_updated: string[];
  reason: string;
  pocs: POC[];
}

export interface CompanyPublicIntelligence {
  company_id: number;
  company_name: string;
  website: string | null;
  linkedin_url: string | null;
  country: string | null;
  industry: string | null;
  wikidata_id: string | null;
  india_locations: string[];
  public_leadership: POC[];
}

export interface PublicIntelligenceTest {
  provider: string;
  result: 'LIVE_VERIFIED' | 'NOT_CONFIGURED' | 'SOURCE_UNAVAILABLE' | 'ERROR';
  status: string;
  message: string | null;
  performed_request: boolean;
  checked_at: string;
}

export async function discoverPublicIntelligence(
  leadId: number, force = false,
): Promise<PublicIntelligenceDiscovery> {
  const { data } = await api.post<PublicIntelligenceDiscovery>(
    `/leads/${leadId}/public-intelligence/discover`, null, { params: { force } });
  return data;
}

export async function fetchCompanyPublicIntelligence(
  companyId: number, signal?: AbortSignal,
): Promise<CompanyPublicIntelligence> {
  const { data } = await api.get<CompanyPublicIntelligence>(
    `/companies/${companyId}/public-intelligence`, { signal });
  return data;
}

export async function testPublicIntelligence(provider = 'wikidata'): Promise<PublicIntelligenceTest> {
  const { data } = await api.post<PublicIntelligenceTest>(
    '/public-intelligence/test', null, { params: { provider } });
  return data;
}
