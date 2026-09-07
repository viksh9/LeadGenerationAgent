import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { fetchTender, fetchTenders, type TenderListParams } from '@/services/tenders';

/** Centralized query keys for the tenders endpoints. */
export const tenderKeys = {
  all: ['tenders'] as const,
  list: (params: TenderListParams) => [...tenderKeys.all, 'list', params] as const,
  detail: (id: string) => [...tenderKeys.all, 'detail', id] as const,
};

/** Paginated public tenders (GET /tenders). */
export function useTenders(params: TenderListParams = {}) {
  return useQuery({
    queryKey: tenderKeys.list(params),
    queryFn: ({ signal }) => fetchTenders(params, signal),
    retry: false,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });
}

/** A single tender (GET /tenders/{id}). */
export function useTender(id: string) {
  return useQuery({
    queryKey: tenderKeys.detail(id),
    queryFn: ({ signal }) => fetchTender(id, signal),
    retry: false,
    staleTime: 30_000,
    enabled: Boolean(id),
  });
}
