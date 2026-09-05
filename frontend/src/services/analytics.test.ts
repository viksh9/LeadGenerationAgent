import { describe, expect, it } from 'vitest';
import {
  buildAnalytics,
  calculateIndustryStats,
  calculateLeadStats,
  calculateOutreachReadiness,
  calculatePriorityDistribution,
  calculateSignalDistribution,
  calculateSourceStats,
  calculateStatusDistribution,
  calculateTechnologyDemand,
  filterAnalyticsLeads,
  rowsToCsv,
} from './analytics';
import type { Lead } from '@/types/lead';
import type { AnalyticsFilters } from '@/types/analytics';

function makeLead(p: Partial<Lead> & Pick<Lead, 'id' | 'company_name'>): Lead {
  return {
    industry: 'IT',
    location: 'Pune',
    company_size: null,
    company_website: null,
    signal_type: 'HIRING',
    signal_title: 'x',
    signal_description: null,
    signal_date: '2026-09-25T00:00:00Z',
    source_name: 'LinkedIn',
    source_url: null,
    technologies: ['Java'],
    project_name: null,
    project_value: null,
    estimated_hiring: 5,
    hiring_roles: [],
    poc_name: null,
    poc_title: 'VP of Engineering',
    poc_linkedin_url: null,
    public_contact: null,
    signal_confidence: 80,
    lead_score: 60,
    lead_priority: 'WARM',
    opportunity_summary: 'x',
    recommended_action: 'x',
    recommended_pitch: 'Subject: hi\n\nbody',
    status: 'NEW',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    last_verified_at: null,
    ...p,
  };
}

const NOW = Date.parse('2026-09-30T00:00:00Z');
const EMPTY: AnalyticsFilters = { range: 'all', industry: '', priority: '', signalType: '', opportunityType: '' };

const LEADS: Lead[] = [
  makeLead({ id: 1, company_name: 'Alpha', industry: 'BFSI', lead_priority: 'HOT', lead_score: 90, signal_type: 'PROJECT_AWARD', estimated_hiring: 40, status: 'QUALIFIED', technologies: ['Java', 'AWS'] }),
  makeLead({ id: 2, company_name: 'Beta', industry: 'BFSI', lead_priority: 'WARM', lead_score: 60, signal_type: 'HIRING', estimated_hiring: 5, technologies: ['Java'] }),
  makeLead({ id: 3, company_name: 'Gamma', industry: 'Healthcare', lead_priority: 'LOW', lead_score: 20, signal_type: 'HIRING', recommended_pitch: null, poc_title: null, source_name: 'News', signal_date: '2026-08-01T00:00:00Z' }),
];

describe('calculateLeadStats', () => {
  it('computes KPIs from lead data', () => {
    const s = calculateLeadStats(LEADS);
    expect(s.totalLeads).toBe(3);
    expect(s.hotLeads).toBe(1);
    expect(s.qualifiedOpportunities).toBe(1); // Alpha QUALIFIED
    expect(s.averageScore).toBe(Math.round((90 + 60 + 20) / 3));
    expect(s.highStaffing).toBe(1); // Alpha (40)
    expect(s.readyForOutreach).toBe(2); // Alpha + Beta
  });
});

describe('distributions', () => {
  it('priority distribution with counts and percentages', () => {
    const d = calculatePriorityDistribution(LEADS);
    const hot = d.find((x) => x.key === 'HOT');
    expect(hot?.count).toBe(1);
    expect(hot?.percentage).toBe(33);
  });
  it('signal distribution uses friendly labels', () => {
    const d = calculateSignalDistribution(LEADS);
    expect(d.find((x) => x.key === 'PROJECT_AWARD')?.label).toBe('Project Award');
  });
  it('status distribution counts current statuses', () => {
    const d = calculateStatusDistribution(LEADS);
    expect(d.find((x) => x.key === 'NEW')?.count).toBe(2);
    expect(d.find((x) => x.key === 'QUALIFIED')?.count).toBe(1);
  });
});

describe('industry / technology / source', () => {
  it('aggregates industry stats with a top opportunity type', () => {
    const rows = calculateIndustryStats(LEADS);
    const bfsi = rows.find((r) => r.industry === 'BFSI');
    expect(bfsi?.leads).toBe(2);
    expect(bfsi?.hotLeads).toBe(1);
  });
  it('ranks technology demand by frequency', () => {
    const techs = calculateTechnologyDemand(LEADS);
    expect(techs[0].technology).toBe('Java'); // in all 3
    expect(techs[0].leadCount).toBe(3);
  });
  it('aggregates source stats', () => {
    const sources = calculateSourceStats(LEADS);
    expect(sources.find((s) => s.source === 'LinkedIn')?.leads).toBe(2);
  });
});

describe('outreach readiness', () => {
  it('counts readiness signals', () => {
    const r = calculateOutreachReadiness(LEADS);
    expect(r.ready).toBe(2);
    expect(r.needsReview).toBe(1);
    expect(r.missingPitch).toBe(1); // Gamma
    expect(r.missingPoc).toBe(1); // Gamma
  });
});

describe('filterAnalyticsLeads', () => {
  it('filters by industry, priority and opportunity type', () => {
    expect(filterAnalyticsLeads(LEADS, { ...EMPTY, industry: 'BFSI' }, NOW)).toHaveLength(2);
    expect(filterAnalyticsLeads(LEADS, { ...EMPTY, priority: 'HOT' }, NOW)).toHaveLength(1);
    // Alpha (PROJECT_AWARD + 40) -> LARGE_SCALE_RAMP_UP
    expect(filterAnalyticsLeads(LEADS, { ...EMPTY, opportunityType: 'LARGE_SCALE_RAMP_UP' }, NOW)).toHaveLength(1);
  });
  it('filters by date range', () => {
    // Gamma signal_date is 2026-08-01 -> outside last 7 days of 2026-09-30.
    const recent = filterAnalyticsLeads(LEADS, { ...EMPTY, range: '7d' }, NOW);
    expect(recent.map((l) => l.company_name)).not.toContain('Gamma');
  });
});

describe('buildAnalytics', () => {
  it('assembles the bundle with top opportunities sorted by score', () => {
    const data = buildAnalytics(LEADS, NOW);
    expect(data.totalConsidered).toBe(3);
    expect(data.topOpportunities[0].company).toBe('Alpha'); // score 90
    expect(data.recentSignals[0].company).toBe('Alpha'); // newest signal (Sep 25) & highest
  });
});

describe('rowsToCsv', () => {
  it('serializes rows and escapes commas/quotes', () => {
    const csv = rowsToCsv(['A', 'B'], [['x', 1], ['has, comma', 2]]);
    expect(csv).toBe('A,B\nx,1\n"has, comma",2');
  });
});
