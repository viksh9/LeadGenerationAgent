import { useMemo } from 'react';
import { useLeads } from './useLeads';
import { buildCompanyIntelligence, buildCompanySummaries } from '@/services/companyIntelligence';
import type { Lead } from '@/types/lead';
import type { CompanyIntelligence, CompanySummary } from '@/types/company';

/**
 * Companies aggregated from a single shared GET /leads query (cached by TanStack
 * Query). LIMITATION: no backend company entity or aggregate endpoint, so
 * companies are grouped client-side (see services/companyIntelligence.ts) over
 * the retrieved dataset (up to COMPANIES_PAGE_SIZE leads, ordered by score).
 */
export const COMPANIES_PAGE_SIZE = 100;

export function useCompanies() {
  const query = useLeads({
    page_size: COMPANIES_PAGE_SIZE,
    sort_by: 'lead_score',
    sort_order: 'desc',
  });

  const companies = useMemo<CompanySummary[] | undefined>(
    () => (query.data ? buildCompanySummaries(query.data.items) : undefined),
    [query.data],
  );

  return {
    companies,
    serverTotal: query.data?.total,
    fetchedCount: query.data?.items.length ?? 0,
    datasetLimited: Boolean(query.data && query.data.total > query.data.items.length),
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: query.refetch,
    isEmpty: Boolean(query.data && query.data.items.length === 0),
  };
}

/**
 * One company's full intelligence profile, aggregated from its leads. Search is
 * a fuzzy backend match (company/signal/project), so results are filtered to an
 * exact company_name match client-side to drop coincidental hits.
 */
export function useCompany(name: string) {
  const query = useLeads({
    search: name,
    page_size: COMPANIES_PAGE_SIZE,
    sort_by: 'lead_score',
    sort_order: 'desc',
  });

  const matches = useMemo<Lead[] | undefined>(
    () => (query.data ? query.data.items.filter((lead) => lead.company_name === name) : undefined),
    [query.data, name],
  );

  const company = useMemo<CompanyIntelligence | undefined>(
    () => (matches && matches.length > 0 ? buildCompanyIntelligence(name, matches) : undefined),
    [matches, name],
  );

  return {
    company,
    isLoading: query.isLoading,
    isError: query.isError,
    isFetching: query.isFetching,
    refetch: query.refetch,
    // Data loaded successfully but no lead carries this exact company name.
    notFound: Boolean(matches && matches.length === 0),
  };
}
