import { useQuery } from '@tanstack/react-query';
import { fetchAIStatus, fetchLeadAI } from '@/services/ai';

/**
 * TanStack Query hooks for the AI intelligence endpoints. The lead detail view
 * and Settings page consume these. AI intelligence is grounded on real data and
 * falls back to a deterministic baseline when no LLM is configured.
 */

/** AI intelligence for a single lead (self-fetched by the panel). */
export function useLeadAI(leadId: number) {
  return useQuery({
    queryKey: ['lead', leadId, 'ai'] as const,
    queryFn: ({ signal }) => fetchLeadAI(leadId, signal),
    enabled: Number.isFinite(leadId),
  });
}

/** Current AI provider configuration/connectivity. */
export function useAiStatus() {
  return useQuery({
    queryKey: ['ai', 'status'] as const,
    queryFn: ({ signal }) => fetchAIStatus(signal),
  });
}
