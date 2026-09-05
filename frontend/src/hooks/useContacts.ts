import { useMemo } from 'react';
import { useLeads } from './useLeads';
import { mapLeadsToContacts } from '@/services/contacts';
import type { ContactRecommendation } from '@/types/contact';

/**
 * Decision-maker role recommendations derived from the shared, cached GET /leads
 * query (no duplicate requests). LIMITATION: no backend Contact entity, so
 * records are derived client-side over the retrieved dataset (up to
 * CONTACTS_PAGE_SIZE leads).
 */
export const CONTACTS_PAGE_SIZE = 100;

export function useContacts() {
  const query = useLeads({
    page_size: CONTACTS_PAGE_SIZE,
    sort_by: 'lead_score',
    sort_order: 'desc',
  });

  const contacts = useMemo<ContactRecommendation[] | undefined>(
    () => (query.data ? mapLeadsToContacts(query.data.items, Date.now()) : undefined),
    [query.data],
  );

  return {
    contacts,
    serverTotal: query.data?.total,
    fetchedCount: query.data?.items.length ?? 0,
    datasetLimited: Boolean(query.data && query.data.total > query.data.items.length),
    isLoading: query.isLoading,
    isError: query.isError,
    isFetching: query.isFetching,
    refetch: query.refetch,
    isEmpty: Boolean(query.data && mapLeadsToContacts(query.data.items).length === 0),
  };
}
