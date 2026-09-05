import { useLeads } from './useLeads';
import type { Lead } from '@/types/lead';

/**
 * Analytics source data. Reuses the shared, cached GET /leads query (no
 * duplicate requests, no per-chart fetch). LIMITATION: no backend analytics
 * endpoint, so metrics are derived over the retrieved dataset (up to
 * ANALYTICS_PAGE_SIZE leads) — the UI labels this "based on available data".
 */
export const ANALYTICS_PAGE_SIZE = 100;

export function useAnalytics() {
  const query = useLeads({
    page_size: ANALYTICS_PAGE_SIZE,
    sort_by: 'lead_score',
    sort_order: 'desc',
  });

  const leads: Lead[] = query.data?.items ?? [];

  return {
    leads,
    serverTotal: query.data?.total,
    fetchedCount: leads.length,
    datasetLimited: Boolean(query.data && query.data.total > leads.length),
    isLoading: query.isLoading,
    isError: query.isError,
    isFetching: query.isFetching,
    refetch: query.refetch,
    isEmpty: Boolean(query.data && leads.length === 0),
  };
}
