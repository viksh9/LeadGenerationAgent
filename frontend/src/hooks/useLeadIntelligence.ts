import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchLeadIntelligence,
  fetchLeadSources,
  refreshLeadIntelligence,
  type LeadIntelligence,
} from '@/services/intelligence';
import { useToast } from '@/contexts/ToastContext';
import type { ApiErrorShape } from '@/services/api';

const errText = (e: unknown, fallback: string): string =>
  (e as ApiErrorShape | undefined)?.message ?? fallback;

export const intelligenceKeys = {
  all: ['intelligence'] as const,
  detail: (leadId: number) => ['intelligence', 'lead', leadId] as const,
  sources: (leadId: number) => ['intelligence', 'sources', leadId] as const,
};

/** Aggregated lead intelligence (GET, cached, no forced provider call). */
export function useLeadIntelligence(leadId: number | undefined) {
  return useQuery({
    queryKey: intelligenceKeys.detail(leadId ?? -1),
    queryFn: ({ signal }) => fetchLeadIntelligence(leadId as number, signal),
    enabled: typeof leadId === 'number' && leadId > 0,
    retry: false,
    staleTime: 60_000,
  });
}

/** All contributing sources for a lead (evidence drawer). */
export function useLeadSources(leadId: number | undefined, enabled = true) {
  return useQuery({
    queryKey: intelligenceKeys.sources(leadId ?? -1),
    queryFn: ({ signal }) => fetchLeadSources(leadId as number, signal),
    enabled: enabled && typeof leadId === 'number' && leadId > 0,
    retry: false,
    staleTime: 60_000,
  });
}

/** Recompute intelligence (bounded AI re-analysis). */
export function useRefreshLeadIntelligence(leadId: number) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation<LeadIntelligence, unknown, void>({
    mutationFn: () => refreshLeadIntelligence(leadId),
    onSuccess: (data) => {
      qc.setQueryData(intelligenceKeys.detail(leadId), data);
      qc.invalidateQueries({ queryKey: intelligenceKeys.sources(leadId) });
      toast.info(data.ai_highlights.ai_available ? 'Intelligence refreshed.' : 'Intelligence refreshed (AI unavailable).');
    },
    onError: (e) => toast.error(errText(e, 'Could not refresh intelligence.')),
  });
}
