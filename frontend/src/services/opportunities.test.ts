import { describe, expect, it } from 'vitest';
import {
  buildOpportunitySummary,
  buildTypeDistribution,
  deriveOpportunityType,
  deriveStaffingNeed,
  deriveUrgency,
  filterOpportunities,
  mapLeadToOpportunity,
  mapLeadsToOpportunities,
  sortOpportunities,
} from './opportunities';
import type { Lead } from '@/types/lead';
import type { OpportunityFilterState } from '@/types/opportunity';

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
    source_name: 'src',
    source_url: null,
    technologies: ['Java'],
    project_name: null,
    project_value: null,
    estimated_hiring: 5,
    hiring_roles: [],
    poc_name: null,
    poc_title: null,
    poc_linkedin_url: null,
    public_contact: null,
    signal_confidence: 80,
    lead_score: 60,
    lead_priority: 'WARM',
    opportunity_summary: null,
    recommended_action: null,
    recommended_pitch: null,
    status: 'NEW',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    last_verified_at: null,
    ...p,
  };
}

const NOW = Date.parse('2026-09-30T00:00:00Z');

const EMPTY_FILTERS: OpportunityFilterState = {
  search: '',
  type: '',
  priority: '',
  staffing: '',
  urgency: '',
  industry: '',
  technology: '',
  status: '',
};

describe('deriveOpportunityType', () => {
  it('maps signal types to opportunity types', () => {
    expect(deriveOpportunityType(makeLead({ id: 1, company_name: 'A', signal_type: 'PROJECT_AWARD', estimated_hiring: 5 }))).toBe('PROJECT_DRIVEN_HIRING');
    expect(deriveOpportunityType(makeLead({ id: 1, company_name: 'A', signal_type: 'HIRING', estimated_hiring: 3 }))).toBe('NORMAL_HIRING');
    expect(deriveOpportunityType(makeLead({ id: 1, company_name: 'A', signal_type: 'HIRING', estimated_hiring: 15 }))).toBe('STAFF_AUGMENTATION');
    expect(deriveOpportunityType(makeLead({ id: 1, company_name: 'A', signal_type: 'HIRING', estimated_hiring: 30 }))).toBe('LARGE_SCALE_RAMP_UP');
    expect(deriveOpportunityType(makeLead({ id: 1, company_name: 'A', signal_type: 'VENDOR_REQUIREMENT' }))).toBe('VENDOR_OPPORTUNITY');
    expect(deriveOpportunityType(makeLead({ id: 1, company_name: 'A', signal_type: 'DIGITAL_TRANSFORMATION' }))).toBe('DIGITAL_TRANSFORMATION');
    expect(deriveOpportunityType(makeLead({ id: 1, company_name: 'A', signal_type: 'TECHNOLOGY_INITIATIVE' }))).toBe('TECHNOLOGY_IMPLEMENTATION');
    expect(deriveOpportunityType(makeLead({ id: 1, company_name: 'A', signal_type: null }))).toBe('LOW_CONFIDENCE');
  });
});

describe('deriveStaffingNeed', () => {
  it('bands estimated hiring', () => {
    expect(deriveStaffingNeed(null)).toBe('UNKNOWN');
    expect(deriveStaffingNeed(0)).toBe('UNKNOWN');
    expect(deriveStaffingNeed(5)).toBe('LOW');
    expect(deriveStaffingNeed(15)).toBe('MEDIUM');
    expect(deriveStaffingNeed(30)).toBe('HIGH');
  });
});

describe('deriveUrgency', () => {
  it('bands signal recency deterministically', () => {
    expect(deriveUrgency('2026-09-25T00:00:00Z', NOW).urgency).toBe('CRITICAL'); // 5 days
    expect(deriveUrgency('2026-09-10T00:00:00Z', NOW).urgency).toBe('HIGH'); // 20 days
    expect(deriveUrgency('2026-08-16T00:00:00Z', NOW).urgency).toBe('MEDIUM'); // 45 days
    expect(deriveUrgency('2026-07-02T00:00:00Z', NOW).urgency).toBe('LOW'); // 90 days
    expect(deriveUrgency(null, NOW).urgency).toBe('UNKNOWN');
  });
});

describe('mapLeadToOpportunity', () => {
  it('preserves lead fields and never fabricates confidence', () => {
    const lead = makeLead({
      id: 7,
      company_name: 'NorthStar',
      lead_score: 92,
      lead_priority: 'HOT',
      technologies: ['Java', 'AWS'],
      recommended_action: 'Engage leadership.',
      estimated_hiring: 40,
    });
    const o = mapLeadToOpportunity(lead, NOW);
    expect(o.leadId).toBe(7);
    expect(o.company).toBe('NorthStar');
    expect(o.score).toBe(92);
    expect(o.priority).toBe('HOT');
    expect(o.technologies).toEqual(['Java', 'AWS']);
    expect(o.recommendedAction).toBe('Engage leadership.');
    expect(o.staffingNeed).toBe('HIGH');
    expect(o.confidence).toBeNull(); // opportunity confidence is not persisted
  });
});

describe('filter/sort/aggregate', () => {
  const leads = [
    makeLead({ id: 1, company_name: 'Alpha', signal_type: 'PROJECT_AWARD', lead_score: 90, lead_priority: 'HOT', estimated_hiring: 30, technologies: ['Java'], status: 'QUALIFIED' }),
    makeLead({ id: 2, company_name: 'Beta', signal_type: 'HIRING', lead_score: 55, lead_priority: 'WARM', estimated_hiring: 5, technologies: ['Python'] }),
    makeLead({ id: 3, company_name: 'Gamma', signal_type: 'VENDOR_REQUIREMENT', lead_score: 70, lead_priority: 'NURTURE', estimated_hiring: null, technologies: ['AWS'] }),
  ];
  const opps = mapLeadsToOpportunities(leads, NOW);

  it('filters by type, priority, technology and search', () => {
    expect(filterOpportunities(opps, { ...EMPTY_FILTERS, priority: 'HOT' })).toHaveLength(1);
    expect(filterOpportunities(opps, { ...EMPTY_FILTERS, type: 'VENDOR_OPPORTUNITY' })[0].company).toBe('Gamma');
    expect(filterOpportunities(opps, { ...EMPTY_FILTERS, technology: 'java' })[0].company).toBe('Alpha');
    expect(filterOpportunities(opps, { ...EMPTY_FILTERS, search: 'beta' })).toHaveLength(1);
  });

  it('sorts by score descending by default', () => {
    const sorted = sortOpportunities(opps, 'score');
    expect(sorted.map((o) => o.company)).toEqual(['Alpha', 'Gamma', 'Beta']);
  });

  it('summarizes the funnel', () => {
    const s = buildOpportunitySummary(opps);
    expect(s.total).toBe(3);
    expect(s.hot).toBe(1);
    expect(s.highStaffing).toBe(1); // Alpha (30)
    expect(s.qualified).toBe(1); // Alpha status QUALIFIED
  });

  it('builds a type distribution of non-empty buckets', () => {
    const dist = buildTypeDistribution(opps);
    const byType = Object.fromEntries(dist.map((d) => [d.type, d.count]));
    expect(byType['LARGE_SCALE_RAMP_UP']).toBe(1); // Alpha (project + 30 hires)
    expect(byType['NORMAL_HIRING']).toBe(1); // Beta
    expect(byType['VENDOR_OPPORTUNITY']).toBe(1); // Gamma
  });
});
