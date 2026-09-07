import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { fetchSignal, fetchSignals, type SignalListParams } from '@/services/signals';

/** Centralized query keys for the signals endpoints. */
export const signalKeys = {
  all: ['signals'] as const,
  list: (params: SignalListParams) => [...signalKeys.all, 'list', params] as const,
  detail: (id: string) => [...signalKeys.all, 'detail', id] as const,
};

/** Paginated verified business signals (GET /signals). */
export function useSignals(params: SignalListParams = {}) {
  return useQuery({
    queryKey: signalKeys.list(params),
    queryFn: ({ signal }) => fetchSignals(params, signal),
    retry: false,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });
}

/** A single verified business signal (GET /signals/{id}). */
export function useSignal(id: string) {
  return useQuery({
    queryKey: signalKeys.detail(id),
    queryFn: ({ signal }) => fetchSignal(id, signal),
    retry: false,
    staleTime: 30_000,
    enabled: Boolean(id),
  });
}
