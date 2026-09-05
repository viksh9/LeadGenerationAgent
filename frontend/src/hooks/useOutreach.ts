import { useMemo } from 'react';
import { useLeads } from './useLeads';
import { mapLeadsToOutreach } from '@/services/outreach';
import type { OutreachItem } from '@/types/outreach';

/**
 * Outreach items derived from the shared, cached GET /leads query (no duplicate
 * requests). LIMITATION: no backend Outreach entity; items are derived
 * client-side over the retrieved dataset (up to OUTREACH_PAGE_SIZE leads).
 */
export const OUTREACH_PAGE_SIZE = 100;

export function useOutreach() {
  const query = useLeads({
    page_size: OUTREACH_PAGE_SIZE,
    sort_by: 'lead_score',
    sort_order: 'desc',
  });

  const items = useMemo<OutreachItem[] | undefined>(
    () => (query.data ? mapLeadsToOutreach(query.data.items, Date.now()) : undefined),
    [query.data],
  );

  return {
    items,
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
