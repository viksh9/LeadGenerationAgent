import { useMemo } from 'react';
import { useLeads } from './useLeads';
import type { Lead, LeadPriority, SignalType } from '@/types/lead';
import type {
  ActivityItem,
  DashboardData,
  DateRange,
  SignalDistributionDatum,
} from '@/types/dashboard';

/**
 * Single shared query powering the whole dashboard. All KPIs, charts, tables and
 * activity are derived from this one dataset (TanStack Query caches it), so the
 * dashboard makes exactly one network request.
 *
 * LIMITATION: the backend has no aggregate/analytics endpoints and no date
 * filter, so aggregates are computed over the retrieved page (up to
 * DASHBOARD_PAGE_SIZE leads, ordered by score) and date filtering is applied
 * client-side. `serverTotal` is the accurate all-leads count from the API.
 */
export const DASHBOARD_PAGE_SIZE = 100;

const PRIORITIES: LeadPriority[] = ['HOT', 'WARM', 'NURTURE', 'LOW'];

const SIGNAL_LABELS: Record<SignalType, string> = {
  HIRING: 'Hiring',
  PROJECT_AWARD: 'Project Award',
  PROJECT_EXECUTION: 'Project Execution',
  EXPANSION: 'Expansion',
  DIGITAL_TRANSFORMATION: 'Digital Transformation',
  TECHNOLOGY_INITIATIVE: 'Technology Initiative',
  VENDOR_REQUIREMENT: 'Vendor Requirement',
  CONTRACT: 'Contract',
  OTHER: 'Other',
};

const DISTRIBUTION_TYPES: SignalType[] = [
  'HIRING',
  'PROJECT_AWARD',
  'PROJECT_EXECUTION',
  'DIGITAL_TRANSFORMATION',
  'EXPANSION',
  'TECHNOLOGY_INITIATIVE',
  'VENDOR_REQUIREMENT',
  'CONTRACT',
];

function withinRange(lead: Lead, range: DateRange): boolean {
  if (range === 'all') return true;
  const stamp = lead.signal_date ?? lead.created_at ?? lead.updated_at;
  if (!stamp) return false;
  const date = new Date(stamp);
  if (Number.isNaN(date.getTime())) return false;
  const days = range === '7d' ? 7 : 30;
  return Date.now() - date.getTime() <= days * 86_400_000;
}

function sortByDateDesc(a: Lead, b: Lead): number {
  const av = new Date(a.signal_date ?? a.created_at ?? 0).getTime();
  const bv = new Date(b.signal_date ?? b.created_at ?? 0).getTime();
  return bv - av;
}

function buildData(items: Lead[], serverTotal: number, range: DateRange): DashboardData {
  const leads = items.filter((lead) => withinRange(lead, range));

  const priorityCounts: Record<LeadPriority, number> = { HOT: 0, WARM: 0, NURTURE: 0, LOW: 0 };
  for (const lead of leads) priorityCounts[lead.lead_priority] += 1;

  const signalCounts = new Map<SignalType, number>();
  for (const lead of leads) {
    if (lead.signal_type) signalCounts.set(lead.signal_type, (signalCounts.get(lead.signal_type) ?? 0) + 1);
  }
  const signalDistribution: SignalDistributionDatum[] = DISTRIBUTION_TYPES.map((type) => ({
    type,
    label: SIGNAL_LABELS[type],
    count: signalCounts.get(type) ?? 0,
  }));

  const byScore = [...leads].sort((a, b) => b.lead_score - a.lead_score);
  const byDate = [...leads].sort(sortByDateDesc);

  const recentActivity: ActivityItem[] = [...leads]
    .sort((a, b) => new Date(b.updated_at ?? 0).getTime() - new Date(a.updated_at ?? 0).getTime())
    .slice(0, 6)
    .map((lead) => ({
      id: lead.id,
      company: lead.company_name,
      at: lead.updated_at ?? lead.created_at,
      kind:
        lead.updated_at && lead.created_at && lead.updated_at !== lead.created_at
          ? 'updated'
          : lead.lead_score > 0
            ? 'analyzed'
            : 'created',
    }));

  return {
    stats: {
      totalInDataset: leads.length,
      serverTotal,
      fetchedCount: items.length,
      datasetLimited: serverTotal > items.length,
      priorityCounts,
      qualifiedCount: leads.filter((lead) => lead.status === 'QUALIFIED').length,
    },
    topOpportunities: byScore.slice(0, 8),
    recentSignals: byDate.filter((lead) => lead.signal_date).slice(0, 6),
    signalDistribution,
    priorityDistribution: PRIORITIES.map((priority) => ({ priority, count: priorityCounts[priority] })),
    recentActivity,
  };
}

export function useDashboard(range: DateRange) {
  const query = useLeads({
    page_size: DASHBOARD_PAGE_SIZE,
    sort_by: 'lead_score',
    sort_order: 'desc',
  });

  const data = useMemo<DashboardData | undefined>(() => {
    if (!query.data) return undefined;
    return buildData(query.data.items, query.data.total, range);
  }, [query.data, range]);

  return {
    data,
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: query.refetch,
    isEmpty: Boolean(query.data && query.data.items.length === 0),
  };
}
