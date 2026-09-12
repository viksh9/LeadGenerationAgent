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

export interface CompanyLocation {
  address_line_1: string | null;
  address_line_2: string | null;
  city: string | null;
  state_or_region: string | null;
  postal_code: string | null;
  country: string | null;
  full_address: string | null;
  location_type: string;
  is_headquarters: boolean;
  source: string | null;
  source_url: string | null;
  trust_score: number;
}

export interface CompanyFieldSource {
  field: string;
  value: string | null;
  source: string | null;
  source_type: string | null;
  source_url: string | null;
  evidence_text: string | null;
  trust_score: number;
  retrieved_at: string | null;
}

export interface CompanyOfficer {
  name: string | null;
  position: string | null;
  start_date: string | null;
  end_date: string | null;
  role_kind: string;
  source: string | null;
  source_url: string | null;
}

export interface CompanyPublicIntelligence {
  company_id: number;
  company_name: string;
  website: string | null;
  linkedin_url: string | null;
  industry: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  full_address: string | null;
  postal_code: string | null;
  company_phone: string | null;
  company_email: string | null;
  contact_url: string | null;
  careers_url: string | null;
  leadership_url: string | null;
  wikidata_id: string | null;
  // Legal / company verification (OpenCorporates) — distinct from the operating brand.
  legal_name: string | null;
  company_number: string | null;
  jurisdiction_code: string | null;
  company_status: string | null;
  incorporation_date: string | null;
  registry_url: string | null;
  opencorporates_url: string | null;
  registered_address: string | null;
  india_entity_type: string | null;
  data_trust_score: number;
  official_verified_at: string | null;
  india_locations: string[];
  locations: CompanyLocation[];
  officers: CompanyOfficer[];
  field_sources: CompanyFieldSource[];
  public_leadership: POC[];
}

export interface CompanyIntelDiscovery {
  company_id: number;
  company_name: string;
  status: 'SUCCESS' | 'PARTIAL' | 'SOURCE_UNAVAILABLE' | 'ERROR';
  provider_status: Record<string, string>;
  fields_updated: string[];
  people_persisted: number;
  data_trust_score: number;
  reason: string;
}

export async function discoverCompanyPublicIntelligence(
  companyId: number, force = false,
): Promise<CompanyIntelDiscovery> {
  const { data } = await api.post<CompanyIntelDiscovery>(
    `/companies/${companyId}/public-intelligence/discover`, null, { params: { force } });
  return data;
}

export async function fetchCompanySources(
  companyId: number, signal?: AbortSignal,
): Promise<CompanyFieldSource[]> {
  const { data } = await api.get<CompanyFieldSource[]>(`/companies/${companyId}/sources`, { signal });
  return data;
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
