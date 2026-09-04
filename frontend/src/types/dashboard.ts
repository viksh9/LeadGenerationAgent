import type { Lead, LeadPriority, SignalType } from './lead';

export type DateRange = 'all' | '7d' | '30d';

export interface DashboardStats {
  /** Leads in the (date-filtered) retrieved dataset. */
  totalInDataset: number;
  /** Server-reported total across all leads (from LeadListResponse.total). */
  serverTotal: number;
  /** Rows actually fetched for this dashboard. */
  fetchedCount: number;
  /** True when more leads exist server-side than were fetched. */
  datasetLimited: boolean;
  priorityCounts: Record<LeadPriority, number>;
  qualifiedCount: number;
}

export interface SignalDistributionDatum {
  type: SignalType;
  label: string;
  count: number;
}

export interface PriorityDistributionDatum {
  priority: LeadPriority;
  count: number;
}

export type ActivityKind = 'created' | 'analyzed' | 'updated';

export interface ActivityItem {
  id: number;
  kind: ActivityKind;
  company: string;
  at: string | null;
}

export interface DashboardData {
  stats: DashboardStats;
  topOpportunities: Lead[];
  recentSignals: Lead[];
  signalDistribution: SignalDistributionDatum[];
  priorityDistribution: PriorityDistributionDatum[];
  recentActivity: ActivityItem[];
}
