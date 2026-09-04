import { useMemo } from 'react';
import { useLeads } from './useLeads';
import type { Lead, LeadPriority } from '@/types/lead';
import type { CompanySummary } from '@/types/company';

/**
 * Companies aggregated from a single shared GET /leads query (cached by TanStack
 * Query). LIMITATION: no backend company entity or aggregate endpoint, so
 * companies are grouped client-side over the retrieved dataset (up to
 * COMPANIES_PAGE_SIZE leads, ordered by score).
 */
export const COMPANIES_PAGE_SIZE = 100;

const PRIORITY_RANK: Record<LeadPriority, number> = { HOT: 3, WARM: 2, NURTURE: 1, LOW: 0 };

function groupByCompany(leads: Lead[]): CompanySummary[] {
  const map = new Map<string, CompanySummary>();
  for (const lead of leads) {
    let company = map.get(lead.company_name);
    if (!company) {
      company = {
        name: lead.company_name,
        industry: lead.industry,
        location: lead.location,
        companySize: lead.company_size,
        website: lead.company_website,
        leadCount: 0,
        bestScore: 0,
        topPriority: 'LOW',
        technologies: [],
        estimatedHiring: 0,
        latestSignal: null,
      };
      map.set(lead.company_name, company);
    }
    company.leadCount += 1;
    company.bestScore = Math.max(company.bestScore, lead.lead_score);
    if (PRIORITY_RANK[lead.lead_priority] > PRIORITY_RANK[company.topPriority]) {
      company.topPriority = lead.lead_priority;
    }
    for (const tech of lead.technologies) {
      if (!company.technologies.includes(tech)) company.technologies.push(tech);
    }
    company.estimatedHiring += lead.estimated_hiring ?? 0;
    company.industry ??= lead.industry;
    company.location ??= lead.location;
    company.website ??= lead.company_website;
    company.companySize ??= lead.company_size;
    if (lead.signal_date && (!company.latestSignal || lead.signal_date > company.latestSignal)) {
      company.latestSignal = lead.signal_date;
    }
  }
  return Array.from(map.values()).sort((a, b) => b.bestScore - a.bestScore);
}

export function useCompanies() {
  const query = useLeads({
    page_size: COMPANIES_PAGE_SIZE,
    sort_by: 'lead_score',
    sort_order: 'desc',
  });

  const companies = useMemo<CompanySummary[] | undefined>(
    () => (query.data ? groupByCompany(query.data.items) : undefined),
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
