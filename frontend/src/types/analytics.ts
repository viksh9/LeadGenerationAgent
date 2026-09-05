import type { LeadPriority, SignalType } from './lead';
import type { OpportunityType, StaffingNeed, Urgency } from './opportunity';

export type DateRange = 'all' | '7d' | '30d' | '90d';

export interface AnalyticsFilters {
  range: DateRange;
  industry: string;
  priority: LeadPriority | '';
  signalType: SignalType | '';
  opportunityType: OpportunityType | '';
}

export interface LeadStatistics {
  totalLeads: number;
  hotLeads: number;
  qualifiedOpportunities: number; // status QUALIFIED/PROPOSAL/WON — not a conversion rate
  averageScore: number;
  highStaffing: number;
  readyForOutreach: number;
}

/** A generic distribution bucket (count + share of the filtered set). */
export interface DistributionDatum {
  key: string;
  label: string;
  count: number;
  percentage: number;
}

export interface IndustryStatistics {
  industry: string;
  leads: number;
  hotLeads: number;
  averageScore: number;
  highStaffing: number;
  topOpportunityType: OpportunityType | null;
  topOpportunityLabel: string | null;
}

export interface TechnologyStatistics {
  technology: string;
  leadCount: number;
  hotLeads: number;
  averageScore: number;
}

export interface LeadTrendPoint {
  date: string; // yyyy-mm-dd
  label: string;
  count: number;
  averageScore: number;
}

export interface OutreachReadiness {
  ready: number;
  needsReview: number;
  missingPoc: number;
  missingPitch: number;
  lowConfidence: number;
}

export interface SourceStatistics {
  source: string;
  leads: number;
  averageScore: number;
  hotLeads: number;
}

export interface RecentSignal {
  leadId: number;
  company: string;
  signalType: SignalType | null;
  signalTitle: string | null;
  score: number;
  priority: LeadPriority;
  date: string | null;
}

export interface TopOpportunityRow {
  leadId: number;
  company: string;
  opportunityType: OpportunityType;
  score: number;
  staffingNeed: StaffingNeed;
  urgency: Urgency;
  priority: LeadPriority;
}

/** The full analytics bundle derived from the filtered lead set. */
export interface AnalyticsData {
  totalConsidered: number;
  stats: LeadStatistics;
  priority: DistributionDatum[];
  signals: DistributionDatum[];
  opportunities: DistributionDatum[];
  status: DistributionDatum[];
  industries: IndustryStatistics[];
  technologies: TechnologyStatistics[];
  scoreTrend: LeadTrendPoint[];
  volumeTrend: LeadTrendPoint[];
  readiness: OutreachReadiness;
  sources: SourceStatistics[];
  recentSignals: RecentSignal[];
  topOpportunities: TopOpportunityRow[];
}
