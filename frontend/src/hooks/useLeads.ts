import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  analyzeLead,
  createLead,
  deleteLead,
  getLead,
  getLeadVerification,
  getLeads,
  updateLead,
} from '@/services/leads';
import { useToast } from '@/contexts/ToastContext';
import type { ApiErrorShape } from '@/services/api';
import type { LeadAnalyzeRequest, LeadCreate, LeadListParams, LeadUpdate } from '@/types/lead';

const errText = (e: unknown, fallback: string) =>
  (e as ApiErrorShape | undefined)?.message ?? fallback;

/**
 * TanStack Query foundation for the lead APIs. The Leads/LeadDetails pages will
 * consume these hooks once those pages are built.
 */

/** Centralized query keys — never scatter key strings across the app. */
export const leadKeys = {
  all: ['leads'] as const,
  lists: () => [...leadKeys.all, 'list'] as const,
  list: (params: LeadListParams) => [...leadKeys.lists(), params] as const,
  detail: (id: number) => [...leadKeys.all, 'detail', id] as const,
};

export function useLeads(params: LeadListParams = {}) {
  return useQuery({
    queryKey: leadKeys.list(params),
    // TanStack passes an AbortSignal so stale search/filter requests are cancelled.
    queryFn: ({ signal }) => getLeads(params, signal),
    // Keep the previous page visible while the next page loads.
    placeholderData: keepPreviousData,
  });
}

export function useLead(id: number) {
  return useQuery({
    queryKey: leadKeys.detail(id),
    queryFn: ({ signal }) => getLead(id, signal),
    enabled: Number.isFinite(id),
  });
}

export function useLeadVerification(id: number) {
  return useQuery({
    queryKey: [...leadKeys.detail(id), 'verification'],
    queryFn: ({ signal }) => getLeadVerification(id, signal),
    enabled: Number.isFinite(id),
  });
}

// Invalidating leadKeys.all cascades to every derived view (dashboard,
// companies, opportunities, contacts, outreach, analytics) — they all read from
// the shared leads query.
export function useCreateLead() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (payload: LeadCreate) => createLead(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: leadKeys.all });
      toast.success('Lead created.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to create lead.')),
  });
}

export function useAnalyzeLead() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (payload: LeadAnalyzeRequest) => analyzeLead(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: leadKeys.all });
      toast.success('Lead analyzed.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to analyze this lead.')),
  });
}

export function useUpdateLead(id: number) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (payload: LeadUpdate) => updateLead(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: leadKeys.detail(id) });
      qc.invalidateQueries({ queryKey: leadKeys.all });
      toast.success('Lead updated successfully.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to update lead.')),
  });
}

export function useDeleteLead() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (id: number) => deleteLead(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: leadKeys.all });
      toast.success('Lead deleted.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to delete lead.')),
  });
}
