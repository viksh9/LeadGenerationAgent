import { useQuery } from '@tanstack/react-query';
import { fetchLeadStakeholders } from '@/services/decisionMakers';

/** Centralized query keys for the lead stakeholders endpoint. */
export const leadStakeholderKeys = {
  all: ['lead-stakeholders'] as const,
  detail: (leadId: number) => [...leadStakeholderKeys.all, leadId] as const,
};

/** Recommended roles + verified people/contacts for a lead (GET /leads/{id}/stakeholders). */
export function useLeadStakeholders(leadId: number) {
  return useQuery({
    queryKey: leadStakeholderKeys.detail(leadId),
    queryFn: ({ signal }) => fetchLeadStakeholders(leadId, signal),
    retry: false,
    staleTime: 30_000,
    enabled: Number.isFinite(leadId),
  });
}
