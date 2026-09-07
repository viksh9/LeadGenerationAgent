import { api } from './api';

export interface BackendCompany {
  id: number;
  canonical_name: string;
  primary_domain: string | null;
  industry: string | null;
  company_type: string | null;
  company_types: string[];
  india_presence: boolean | null;
  india_locations: string[];
  identity_confidence: number;
  evidence_confidence: number;
  verification_status: string;
  data_provenance: string;
}

export interface CompanyIntelligenceProfile {
  identity: Record<string, unknown>;
  geography: { india_presence: boolean | null; india_locations: string[]; headquarters_city: string | null };
  hiring: {
    canonical_active_openings: number;
    recent_openings: number;
    hiring_intensity: string | null;
    hiring_trend: string;
    role_demand: { role: string; active_jobs: number; demand_strength: string }[];
  };
  technology_demand: { technology: string; active_jobs: number; recent_jobs: number; demand_strength: string }[];
  location_intelligence: { hiring_locations: { city: string; job_count: number }[]; office_location: string | null; note: string };
  signals: { signal_type: string; signal_title: string | null; strength: string }[];
  opportunity: Record<string, unknown> | null;
  evidence: {
    verification_status: string;
    evidence_confidence: number;
    source_reliability: number;
    supporting_source_count: number;
    independent_support_count: number;
  };
}

export async function searchCompanies(search: string, signal?: AbortSignal): Promise<BackendCompany[]> {
  const { data } = await api.get<{ items: BackendCompany[] }>('/companies', {
    params: { search, page_size: 5 },
    signal,
  });
  return data.items;
}

export async function getCompanyIntelligence(id: number, signal?: AbortSignal): Promise<CompanyIntelligenceProfile> {
  const { data } = await api.get<CompanyIntelligenceProfile>(`/companies/${id}/intelligence`, { signal });
  return data;
}

export async function getCompanyHistory(id: number, signal?: AbortSignal): Promise<{ events: { event_type: string; description: string }[] }> {
  const { data } = await api.get<{ events: { event_type: string; description: string }[] }>(
    `/companies/${id}/history`,
    { signal },
  );
  return data;
}
