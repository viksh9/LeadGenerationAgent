import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { fetchContact, fetchContacts, type ContactsParams } from '@/services/decisionMakers';

/** Centralized query keys for the real decision-maker / contact endpoints. */
export const verifiedContactKeys = {
  all: ['verified-contacts'] as const,
  list: (params: ContactsParams) => [...verifiedContactKeys.all, 'list', params] as const,
  detail: (id: string) => [...verifiedContactKeys.all, 'detail', id] as const,
};

/** Paginated real decision-makers / business contacts (GET /contacts). */
export function useVerifiedContacts(params: ContactsParams = {}) {
  return useQuery({
    queryKey: verifiedContactKeys.list(params),
    queryFn: ({ signal }) => fetchContacts(params, signal),
    retry: false,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });
}

/** A single real decision-maker / contact (GET /contacts/{id}). */
export function useVerifiedContact(id: string) {
  return useQuery({
    queryKey: verifiedContactKeys.detail(id),
    queryFn: ({ signal }) => fetchContact(id, signal),
    retry: false,
    staleTime: 30_000,
    enabled: Boolean(id),
  });
}
