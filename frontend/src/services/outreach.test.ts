import { describe, expect, it } from 'vitest';
import {
  buildOutreachSummary,
  deriveMessageStrategy,
  deriveOutreachStatus,
  filterOutreach,
  mapLeadToOutreach,
  mapLeadsToOutreach,
  parsePitch,
  sortOutreach,
  splitQueue,
} from './outreach';
import type { Lead } from '@/types/lead';
import type { OutreachFilterState } from '@/types/outreach';

function makeLead(p: Partial<Lead> & Pick<Lead, 'id' | 'company_name'>): Lead {
  return {
    normalized_company_name: null,
    company_domain: null,
    company_type: null,
    it_job_count: 0,
    recent_job_count: 0,
    hiring_intensity: null,
    primary_target_role: null,
    company_signals: [],
    data_provenance: 'REAL',
    source_count: 0,
    evidence: [],
    last_signal_date: null,
    industry: 'IT',
    location: 'Pune',
    company_size: null,
    company_website: null,
    signal_type: 'PROJECT_AWARD',
    signal_title: 'x',
    signal_description: null,
    signal_date: '2026-09-20T00:00:00Z',
    source_name: 'src',
    source_url: null,
    technologies: ['Java'],
    project_name: null,
    project_value: null,
    estimated_hiring: 40,
    hiring_roles: [],
    poc_name: null,
    poc_title: 'VP of Engineering',
    poc_linkedin_url: null,
    public_contact: null,
    signal_confidence: 90,
    lead_score: 88,
    lead_priority: 'HOT',
    opportunity_summary: 'Large ramp-up.',
    recommended_action: 'Engage leadership.',
    recommended_pitch: 'Subject: Scaling your team\n\nWe noticed you are hiring.',
    status: 'NEW',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    last_verified_at: null,
    ...p,
  };
}

const NOW = Date.parse('2026-09-30T00:00:00Z');
const EMPTY: OutreachFilterState = {
  search: '', priority: '', industry: '', opportunityType: '', role: '', status: '', minScore: '',
};

describe('parsePitch', () => {
  it('splits a subject line from the body', () => {
    const { subject, body } = parsePitch('Subject: Hello\n\nThe body.');
    expect(subject).toBe('Hello');
    expect(body).toBe('The body.');
  });
  it('returns no subject when absent', () => {
    expect(parsePitch('Plain text.').subject).toBeNull();
  });
});

describe('deriveMessageStrategy', () => {
  it('maps opportunity type to a strategy', () => {
    expect(deriveMessageStrategy('LARGE_SCALE_RAMP_UP')).toBe('PROJECT_RAMP_UP');
    expect(deriveMessageStrategy('STAFF_AUGMENTATION')).toBe('STAFF_AUGMENTATION');
    expect(deriveMessageStrategy('VENDOR_OPPORTUNITY')).toBe('VENDOR_OPPORTUNITY');
    expect(deriveMessageStrategy('DIGITAL_TRANSFORMATION')).toBe('DIGITAL_TRANSFORMATION');
    expect(deriveMessageStrategy('NORMAL_HIRING')).toBe('NORMAL_HIRING');
    expect(deriveMessageStrategy('LOW_CONFIDENCE')).toBe('NURTURE');
  });
});

describe('deriveOutreachStatus', () => {
  it('maps lead status to a preparation status', () => {
    expect(deriveOutreachStatus(makeLead({ id: 1, company_name: 'A', status: 'NEW' }))).toBe('READY');
    expect(deriveOutreachStatus(makeLead({ id: 1, company_name: 'A', status: 'NEW', recommended_pitch: null }))).toBe('DRAFT');
    expect(deriveOutreachStatus(makeLead({ id: 1, company_name: 'A', status: 'CONTACTED' }))).toBe('CONTACTED');
    expect(deriveOutreachStatus(makeLead({ id: 1, company_name: 'A', status: 'REPLIED' }))).toBe('RESPONDED');
    expect(deriveOutreachStatus(makeLead({ id: 1, company_name: 'A', status: 'WON' }))).toBe('COMPLETED');
  });
});

describe('mapLeadToOutreach', () => {
  it('derives message, context and strategy without fabricating channels', () => {
    const o = mapLeadToOutreach(makeLead({ id: 7, company_name: 'NorthStar' }), NOW);
    expect(o.message.subject).toBe('Scaling your team');
    expect(o.opportunityType).toBe('LARGE_SCALE_RAMP_UP'); // PROJECT_AWARD + 40 hires
    expect(o.messageStrategy).toBe('PROJECT_RAMP_UP');
    expect(o.staffingNeed).toBe('HIGH');
    expect(o.pitchConfidence).toBeNull(); // not persisted
    expect(o.message.linkedin).toBeNull(); // not persisted
    expect(o.message.talkingPoints).toEqual([]); // not persisted
    expect(o.ready).toBe(true); // HOT + pitch + role
  });

  it('flags needs-review reasons when data is missing', () => {
    const o = mapLeadToOutreach(
      makeLead({ id: 8, company_name: 'Weak', recommended_pitch: null, poc_title: null, lead_priority: 'LOW' }),
      NOW,
    );
    expect(o.ready).toBe(false);
    expect(o.reviewReasons).toContain('No pitch generated');
    expect(o.reviewReasons).toContain('No target role identified');
  });
});

describe('queue split / filter / sort / summary', () => {
  const leads = [
    makeLead({ id: 1, company_name: 'Alpha', lead_priority: 'HOT', lead_score: 90, status: 'NEW' }),
    makeLead({ id: 2, company_name: 'Beta', lead_priority: 'WARM', lead_score: 70, status: 'CONTACTED' }),
    makeLead({ id: 3, company_name: 'Gamma', lead_priority: 'LOW', lead_score: 30, recommended_pitch: null, poc_title: null }),
  ];
  const items = mapLeadsToOutreach(leads, NOW);

  it('splits ready vs needs-review', () => {
    const { ready, needsReview } = splitQueue(items);
    expect(ready.map((i) => i.company)).toEqual(['Alpha', 'Beta']); // HOT before WARM
    expect(needsReview.map((i) => i.company)).toEqual(['Gamma']);
  });

  it('filters by priority, status and min score', () => {
    expect(filterOutreach(items, { ...EMPTY, priority: 'HOT' })).toHaveLength(1);
    expect(filterOutreach(items, { ...EMPTY, status: 'CONTACTED' })[0].company).toBe('Beta');
    expect(filterOutreach(items, { ...EMPTY, minScore: '80' })).toHaveLength(1);
  });

  it('sorts by priority (HOT first) by default', () => {
    expect(sortOutreach(items, 'priority').map((i) => i.company)).toEqual(['Alpha', 'Beta', 'Gamma']);
  });

  it('summarizes readiness', () => {
    const s = buildOutreachSummary(items);
    expect(s.ready).toBe(2);
    expect(s.needsReview).toBe(1);
    expect(s.hot).toBe(1);
    expect(s.inProgress).toBe(1); // Beta CONTACTED
  });
});
