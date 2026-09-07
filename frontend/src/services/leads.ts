import { api } from './api';
import type {
  Lead,
  LeadAnalysis,
  LeadAnalyzeRequest,
  LeadCreate,
  LeadListParams,
  LeadListResponse,
  LeadUpdate,
  TechnologyDemandResponse,
} from '@/types/lead';

/**
 * Thin API client for the lead endpoints. No business logic lives here — these
 * are 1:1 wrappers around the FastAPI routes, kept out of React components.
 */

export async function getLeads(
  params: LeadListParams = {},
  signal?: AbortSignal,
): Promise<LeadListResponse> {
  const { data } = await api.get<LeadListResponse>('/leads', { params, signal });
  return data;
}

export async function getLead(id: number, signal?: AbortSignal): Promise<Lead> {
  const { data } = await api.get<Lead>(`/leads/${id}`, { signal });
  return data;
}

export async function getTechnologyDemand(
  params: { provenance?: 'real' | 'synthetic' | 'all'; limit?: number } = {},
  signal?: AbortSignal,
): Promise<TechnologyDemandResponse> {
  const { data } = await api.get<TechnologyDemandResponse>('/leads/technology-demand', {
    params,
    signal,
  });
  return data;
}

export async function createLead(payload: LeadCreate): Promise<Lead> {
  const { data } = await api.post<Lead>('/leads', payload);
  return data;
}

export async function analyzeLead(payload: LeadAnalyzeRequest): Promise<LeadAnalysis> {
  const { data } = await api.post<LeadAnalysis>('/leads/analyze', payload);
  return data;
}

export async function updateLead(id: number, payload: LeadUpdate): Promise<Lead> {
  const { data } = await api.put<Lead>(`/leads/${id}`, payload);
  return data;
}

export async function deleteLead(id: number): Promise<void> {
  await api.delete(`/leads/${id}`);
}
