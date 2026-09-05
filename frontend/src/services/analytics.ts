import type { Lead, LeadPriority, LeadStatus } from '@/types/lead';
import type {
  AnalyticsData,
  AnalyticsFilters,
  DistributionDatum,
  IndustryStatistics,
  LeadStatistics,
  LeadTrendPoint,
  OutreachReadiness,
  SourceStatistics,
  TechnologyStatistics,
} from '@/types/analytics';
import type { OpportunityType } from '@/types/opportunity';
import { PRIORITIES, SIGNAL_LABELS, SIGNAL_TYPES, STATUSES, humanizeSignal } from '@/constants/leads';
import {
  OPPORTUNITY_TYPES,
  OPPORTUNITY_TYPE_LABELS,
  deriveOpportunityType,
  deriveStaffingNeed,
  deriveUrgency,
} from '@/services/opportunities';

/**
 * Analytics transformation layer.
 *
 * TEMPORARY STRATEGY (Phase 1): no backend analytics/aggregate endpoint. All
 * metrics are derived from the leads already fetched (capped at ~100 — see
 * hooks/useAnalytics), so the UI labels analytics "based on available lead
 * data". IMPORTANT: status counts are a CURRENT distribution, never a
 * historical conversion rate; no revenue metrics exist.
 */

const DAY_MS = 86_400_000;
const QUALIFIED: LeadStatus[] = ['QUALIFIED', 'PROPOSAL', 'WON'];
const PRIORITY_LABELS: Record<LeadPriority, string> = {
  HOT: 'Hot',
  WARM: 'Warm',
  NURTURE: 'Nurture',
  LOW: 'Low',
};
const RANGE_DAYS: Record<Exclude<AnalyticsFilters['range'], 'all'>, number> = {
  '7d': 7,
  '30d': 30,
  '90d': 90,
};

const avg = (values: number[]): number =>
  values.length ? Math.round(values.reduce((s, v) => s + v, 0) / values.length) : 0;

function dateKey(lead: Lead): string | null {
  const iso = lead.signal_date ?? lead.created_at;
  return iso ? iso.slice(0, 10) : null;
}

function isReadyForOutreach(lead: Lead): boolean {
  return (
    (lead.lead_priority === 'HOT' || lead.lead_priority === 'WARM') &&
    Boolean(lead.recommended_pitch) &&
    Boolean(lead.poc_title) &&
    !(lead.signal_confidence != null && lead.signal_confidence < 50)
  );
}

/** Apply the analytics filters (client-side; date range uses signal/created date). */
export function filterAnalyticsLeads(leads: Lead[], f: AnalyticsFilters, now: number): Lead[] {
  const industry = f.industry.trim().toLowerCase();
  const cutoff = f.range === 'all' ? null : now - RANGE_DAYS[f.range] * DAY_MS;
  return leads.filter((lead) => {
    if (f.priority && lead.lead_priority !== f.priority) return false;
    if (f.signalType && lead.signal_type !== f.signalType) return false;
    if (industry && !(lead.industry ?? '').toLowerCase().includes(industry)) return false;
    if (f.opportunityType && deriveOpportunityType(lead) !== f.opportunityType) return false;
    if (cutoff != null) {
      const iso = lead.signal_date ?? lead.created_at;
      const ts = iso ? new Date(iso).getTime() : NaN;
      if (Number.isNaN(ts) || ts < cutoff) return false;
    }
    return true;
  });
}

function distribution<K extends string>(
  leads: Lead[],
  keyFor: (lead: Lead) => K | null,
  labelFor: (k: K) => string,
  order: readonly K[],
): DistributionDatum[] {
  const counts = new Map<K, number>();
  for (const lead of leads) {
    const k = keyFor(lead);
    if (k != null) counts.set(k, (counts.get(k) ?? 0) + 1);
  }
  const total = leads.length;
  return order
    .filter((k) => (counts.get(k) ?? 0) > 0)
    .map((k) => ({
      key: k,
      label: labelFor(k),
      count: counts.get(k) as number,
      percentage: total ? Math.round(((counts.get(k) as number) / total) * 100) : 0,
    }));
}

export function calculateLeadStats(leads: Lead[]): LeadStatistics {
  return {
    totalLeads: leads.length,
    hotLeads: leads.filter((l) => l.lead_priority === 'HOT').length,
    qualifiedOpportunities: leads.filter((l) => QUALIFIED.includes(l.status)).length,
    averageScore: avg(leads.map((l) => l.lead_score)),
    highStaffing: leads.filter((l) => deriveStaffingNeed(l.estimated_hiring) === 'HIGH').length,
    readyForOutreach: leads.filter(isReadyForOutreach).length,
  };
}

export const calculatePriorityDistribution = (leads: Lead[]) =>
  distribution(leads, (l) => l.lead_priority, (k) => PRIORITY_LABELS[k], PRIORITIES);

export const calculateSignalDistribution = (leads: Lead[]) =>
  distribution(leads, (l) => l.signal_type, (k) => SIGNAL_LABELS[k], SIGNAL_TYPES);

export const calculateOpportunityDistribution = (leads: Lead[]) =>
  distribution(leads, (l) => deriveOpportunityType(l), (k) => OPPORTUNITY_TYPE_LABELS[k], OPPORTUNITY_TYPES);

export const calculateStatusDistribution = (leads: Lead[]) =>
  distribution(leads, (l) => l.status, (k) => k, STATUSES);

export function calculateIndustryStats(leads: Lead[]): IndustryStatistics[] {
  const groups = new Map<string, Lead[]>();
  for (const lead of leads) {
    const key = lead.industry ?? 'Unknown';
    (groups.get(key) ?? groups.set(key, []).get(key)!).push(lead);
  }
  return Array.from(groups.entries())
    .map(([industry, group]) => {
      const oppCounts = new Map<OpportunityType, number>();
      for (const l of group) {
        const t = deriveOpportunityType(l);
        oppCounts.set(t, (oppCounts.get(t) ?? 0) + 1);
      }
      const top = [...oppCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
      return {
        industry,
        leads: group.length,
        hotLeads: group.filter((l) => l.lead_priority === 'HOT').length,
        averageScore: avg(group.map((l) => l.lead_score)),
        highStaffing: group.filter((l) => deriveStaffingNeed(l.estimated_hiring) === 'HIGH').length,
        topOpportunityType: top,
        topOpportunityLabel: top ? OPPORTUNITY_TYPE_LABELS[top] : null,
      };
    })
    .sort((a, b) => b.leads - a.leads);
}

export function calculateTechnologyDemand(leads: Lead[], limit = 10): TechnologyStatistics[] {
  const map = new Map<string, Lead[]>();
  for (const lead of leads) {
    for (const tech of lead.technologies ?? []) {
      (map.get(tech) ?? map.set(tech, []).get(tech)!).push(lead);
    }
  }
  return Array.from(map.entries())
    .map(([technology, group]) => ({
      technology,
      leadCount: group.length,
      hotLeads: group.filter((l) => l.lead_priority === 'HOT').length,
      averageScore: avg(group.map((l) => l.lead_score)),
    }))
    .sort((a, b) => b.leadCount - a.leadCount || b.averageScore - a.averageScore)
    .slice(0, limit);
}

function trend(leads: Lead[]): { date: string; leads: Lead[] }[] {
  const map = new Map<string, Lead[]>();
  for (const lead of leads) {
    const key = dateKey(lead);
    if (!key) continue;
    (map.get(key) ?? map.set(key, []).get(key)!).push(lead);
  }
  return Array.from(map.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([date, group]) => ({ date, leads: group }));
}

function trendLabel(date: string): string {
  const d = new Date(`${date}T00:00:00Z`);
  return Number.isNaN(d.getTime())
    ? date
    : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

export function calculateLeadTrend(leads: Lead[]): { score: LeadTrendPoint[]; volume: LeadTrendPoint[] } {
  const buckets = trend(leads);
  const points: LeadTrendPoint[] = buckets.map(({ date, leads: group }) => ({
    date,
    label: trendLabel(date),
    count: group.length,
    averageScore: avg(group.map((l) => l.lead_score)),
  }));
  return { score: points, volume: points };
}

export function calculateOutreachReadiness(leads: Lead[]): OutreachReadiness {
  return {
    ready: leads.filter(isReadyForOutreach).length,
    needsReview: leads.filter((l) => !isReadyForOutreach(l)).length,
    missingPoc: leads.filter((l) => !l.poc_title).length,
    missingPitch: leads.filter((l) => !l.recommended_pitch).length,
    lowConfidence: leads.filter((l) => l.signal_confidence != null && l.signal_confidence < 50).length,
  };
}

export function calculateSourceStats(leads: Lead[]): SourceStatistics[] {
  const map = new Map<string, Lead[]>();
  for (const lead of leads) {
    if (!lead.source_name) continue;
    (map.get(lead.source_name) ?? map.set(lead.source_name, []).get(lead.source_name)!).push(lead);
  }
  return Array.from(map.entries())
    .map(([source, group]) => ({
      source,
      leads: group.length,
      averageScore: avg(group.map((l) => l.lead_score)),
      hotLeads: group.filter((l) => l.lead_priority === 'HOT').length,
    }))
    .sort((a, b) => b.leads - a.leads);
}

export function buildAnalytics(leads: Lead[], now: number): AnalyticsData {
  const byScore = [...leads].sort((a, b) => b.lead_score - a.lead_score);
  const { score, volume } = calculateLeadTrend(leads);
  return {
    totalConsidered: leads.length,
    stats: calculateLeadStats(leads),
    priority: calculatePriorityDistribution(leads),
    signals: calculateSignalDistribution(leads),
    opportunities: calculateOpportunityDistribution(leads),
    status: calculateStatusDistribution(leads),
    industries: calculateIndustryStats(leads),
    technologies: calculateTechnologyDemand(leads),
    scoreTrend: score,
    volumeTrend: volume,
    readiness: calculateOutreachReadiness(leads),
    sources: calculateSourceStats(leads),
    recentSignals: [...leads]
      .filter((l) => l.signal_date)
      .sort((a, b) => (b.signal_date ?? '').localeCompare(a.signal_date ?? '') || b.lead_score - a.lead_score)
      .slice(0, 8)
      .map((l) => ({
        leadId: l.id,
        company: l.company_name,
        signalType: l.signal_type,
        signalTitle: l.signal_title,
        score: l.lead_score,
        priority: l.lead_priority,
        date: l.signal_date,
      })),
    topOpportunities: byScore.slice(0, 8).map((l) => ({
      leadId: l.id,
      company: l.company_name,
      opportunityType: deriveOpportunityType(l),
      score: l.lead_score,
      staffingNeed: deriveStaffingNeed(l.estimated_hiring),
      urgency: deriveUrgency(l.signal_date, now).urgency,
      priority: l.lead_priority,
    })),
  };
}

/** Serialize rows to CSV (client-side export of analytics tables). */
export function rowsToCsv(headers: string[], rows: (string | number)[][]): string {
  const esc = (v: string | number) => {
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [headers, ...rows].map((r) => r.map(esc).join(',')).join('\n');
}

export { humanizeSignal, OPPORTUNITY_TYPE_LABELS };
