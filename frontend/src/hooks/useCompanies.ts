import { useMemo } from 'react';
import { useLeads } from './useLeads';
import type { Lead, LeadPriority } from '@/types/lead';
import type { CompanyDetail, CompanySummary } from '@/types/company';

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

const EMPTY_PRIORITY_COUNTS: Record<LeadPriority, number> = { HOT: 0, WARM: 0, NURTURE: 0, LOW: 0 };

function aggregateDetail(name: string, leads: Lead[]): CompanyDetail {
  // Leads arrive sorted by score desc, so the first is the strongest signal.
  const detail: CompanyDetail = {
    name,
    industry: null,
    location: null,
    companySize: null,
    website: null,
    leadCount: leads.length,
    bestScore: 0,
    topPriority: 'LOW',
    technologies: [],
    estimatedHiring: 0,
    latestSignal: null,
    priorityCounts: { ...EMPTY_PRIORITY_COUNTS },
    leads,
    contacts: [],
  };

  const seenContacts = new Set<string>();
  for (const lead of leads) {
    detail.bestScore = Math.max(detail.bestScore, lead.lead_score);
    if (PRIORITY_RANK[lead.lead_priority] > PRIORITY_RANK[detail.topPriority]) {
      detail.topPriority = lead.lead_priority;
    }
    detail.priorityCounts[lead.lead_priority] += 1;
    for (const tech of lead.technologies) {
      if (!detail.technologies.includes(tech)) detail.technologies.push(tech);
    }
    detail.estimatedHiring += lead.estimated_hiring ?? 0;
    detail.industry ??= lead.industry;
    detail.location ??= lead.location;
    detail.website ??= lead.company_website;
    detail.companySize ??= lead.company_size;
    if (lead.signal_date && (!detail.latestSignal || lead.signal_date > detail.latestSignal)) {
      detail.latestSignal = lead.signal_date;
    }
    if (lead.poc_name && !seenContacts.has(lead.poc_name)) {
      seenContacts.add(lead.poc_name);
      detail.contacts.push({
        name: lead.poc_name,
        title: lead.poc_title,
        linkedinUrl: lead.poc_linkedin_url,
      });
    }
  }
  return detail;
}

/**
 * One company's full profile, aggregated from its leads. Search is a fuzzy
 * backend match (company/signal/project), so results are filtered to an exact
 * company_name match client-side to drop coincidental hits.
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

  const company = useMemo<CompanyDetail | undefined>(
    () => (matches && matches.length > 0 ? aggregateDetail(name, matches) : undefined),
    [matches, name],
  );

  return {
    company,
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: query.refetch,
    // Data loaded successfully but no lead carries this exact company name.
    notFound: Boolean(matches && matches.length === 0),
  };
}
