import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  analyzeLead,
  createLead,
  deleteLead,
  getLead,
  getLeads,
  updateLead,
} from '@/services/leads';
import type { LeadCreate, LeadListParams, LeadUpdate } from '@/types/lead';

/**
 * TanStack Query foundation for the lead APIs. The Leads/LeadDetails pages will
 * consume these hooks once those pages are built.
 */

export const leadKeys = {
  all: ['leads'] as const,
  list: (params: LeadListParams) => [...leadKeys.all, 'list', params] as const,
  detail: (id: number) => [...leadKeys.all, 'detail', id] as const,
};

export function useLeads(params: LeadListParams = {}) {
  return useQuery({
    queryKey: leadKeys.list(params),
    queryFn: () => getLeads(params),
    // Keep the previous page visible while the next page loads.
    placeholderData: keepPreviousData,
  });
}

export function useLead(id: number) {
  return useQuery({
    queryKey: leadKeys.detail(id),
    queryFn: () => getLead(id),
    enabled: Number.isFinite(id),
  });
}

export function useCreateLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: LeadCreate) => createLead(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: leadKeys.all }),
  });
}

export function useAnalyzeLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: analyzeLead,
    onSuccess: () => qc.invalidateQueries({ queryKey: leadKeys.all }),
  });
}

export function useUpdateLead(id: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: LeadUpdate) => updateLead(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: leadKeys.detail(id) });
      qc.invalidateQueries({ queryKey: leadKeys.all });
    },
  });
}

export function useDeleteLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteLead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: leadKeys.all }),
  });
}
