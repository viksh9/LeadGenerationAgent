import { useMemo } from 'react';
import { useLeads } from './useLeads';
import { mapLeadsToOpportunities } from '@/services/opportunities';
import type { Opportunity } from '@/types/opportunity';

/**
 * Opportunities derived from the shared GET /leads query (cached by TanStack
 * Query — no duplicate requests). LIMITATION: no backend opportunity endpoint,
 * so records are derived client-side over the retrieved dataset (up to
 * OPPORTUNITIES_PAGE_SIZE leads, ordered by score).
 */
export const OPPORTUNITIES_PAGE_SIZE = 100;

export function useOpportunities() {
  const query = useLeads({
    page_size: OPPORTUNITIES_PAGE_SIZE,
    sort_by: 'lead_score',
    sort_order: 'desc',
  });

  const opportunities = useMemo<Opportunity[] | undefined>(
    // Date.now() is read once per data change; urgency is recency-based.
    () => (query.data ? mapLeadsToOpportunities(query.data.items, Date.now()) : undefined),
    [query.data],
  );

  return {
    opportunities,
    serverTotal: query.data?.total,
    fetchedCount: query.data?.items.length ?? 0,
    datasetLimited: Boolean(query.data && query.data.total > query.data.items.length),
    isLoading: query.isLoading,
    isError: query.isError,
    isFetching: query.isFetching,
    refetch: query.refetch,
    isEmpty: Boolean(query.data && query.data.items.length === 0),
  };
}
