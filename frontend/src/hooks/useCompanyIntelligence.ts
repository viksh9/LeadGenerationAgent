import { useQuery } from '@tanstack/react-query';
import { getCompanyHistory, getCompanyIntelligence, searchCompanies } from '@/services/companies';

/**
 * Backend company intelligence resolved by company name. Returns null (not an
 * error) when there is no verified backend company entity yet — the caller shows
 * an honest "no verified data" state.
 */
export function useCompanyIntelligence(name: string) {
  return useQuery({
    queryKey: ['company-intelligence', name],
    enabled: Boolean(name),
    queryFn: async ({ signal }) => {
      const matches = await searchCompanies(name, signal);
      const exact =
        matches.find((c) => c.canonical_name.toLowerCase() === name.toLowerCase()) ?? matches[0];
      if (!exact) return null;
      const [profile, history] = await Promise.all([
        getCompanyIntelligence(exact.id, signal),
        getCompanyHistory(exact.id, signal),
      ]);
      return { company: exact, profile, history: history.events };
    },
  });
}
