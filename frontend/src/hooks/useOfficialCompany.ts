import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { searchCompanies } from '@/services/companies';
import {
  discoverCompanyPublicIntelligence,
  fetchCompanyPublicIntelligence,
  type CompanyIntelDiscovery,
} from '@/services/publicIntelligence';
import { useToast } from '@/contexts/ToastContext';
import type { ApiErrorShape } from '@/services/api';

const errText = (e: unknown, fallback: string): string =>
  (e as ApiErrorShape | undefined)?.message ?? fallback;

export const officialCompanyKeys = {
  byName: (name: string) => ['official-company', 'name', name] as const,
};

/**
 * Official company intelligence resolved by company name (search → exact id →
 * profile). Returns null (not an error) when no backend Company entity exists yet.
 */
export function useCompanyPublicIntelligence(name: string) {
  return useQuery({
    queryKey: officialCompanyKeys.byName(name),
    enabled: Boolean(name),
    retry: false,
    staleTime: 60_000,
    queryFn: async ({ signal }) => {
      const matches = await searchCompanies(name, signal);
      const exact =
        matches.find((c) => c.canonical_name.toLowerCase() === name.toLowerCase()) ?? matches[0];
      if (!exact) return null;
      return fetchCompanyPublicIntelligence(exact.id, signal);
    },
  });
}

/** Run official-company discovery for a resolved company id. */
export function useDiscoverCompanyIntelligence(name: string) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation<CompanyIntelDiscovery, unknown, number>({
    mutationFn: (companyId) => discoverCompanyPublicIntelligence(companyId),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: officialCompanyKeys.byName(name) });
      const map: Record<string, string> = {
        SUCCESS: `Discovered official company facts (trust ${res.data_trust_score}%).`,
        PARTIAL: 'Discovered partial official company facts.',
        SOURCE_UNAVAILABLE: 'Official company sources could not be accessed.',
        ERROR: 'Discovery failed.',
      };
      toast.info(map[res.status] ?? res.reason);
    },
    onError: (e) => toast.error(errText(e, 'Official company discovery could not run.')),
  });
}
