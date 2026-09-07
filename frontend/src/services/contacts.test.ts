import { describe, expect, it } from 'vitest';
import {
  buildContactSummary,
  buildTopTargetRoles,
  deriveDecisionMakerType,
  filterContacts,
  groupByCompany,
  mapLeadToContactRecommendations,
  mapLeadsToContacts,
  relevanceBand,
  sortContacts,
} from './contacts';
import type { Lead } from '@/types/lead';
import type { ContactFilterState } from '@/types/contact';

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
    signal_type: 'HIRING',
    signal_title: 'x',
    signal_description: null,
    signal_date: '2026-09-20T00:00:00Z',
    source_name: 'src',
    source_url: null,
    technologies: [],
    project_name: null,
    project_value: null,
    estimated_hiring: 10,
    hiring_roles: [],
    poc_name: null,
    poc_title: 'VP of Engineering',
    poc_linkedin_url: null,
    public_contact: null,
    signal_confidence: 80,
    lead_score: 88,
    lead_priority: 'HOT',
    opportunity_summary: null,
    recommended_action: 'Engage leadership.',
    recommended_pitch: null,
    status: 'NEW',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    last_verified_at: null,
    ...p,
  };
}

const NOW = Date.parse('2026-09-30T00:00:00Z');
const EMPTY: ContactFilterState = {
  search: '', type: '', role: '', priority: '', industry: '', opportunityType: '', confidence: '', minRelevance: '',
};

describe('deriveDecisionMakerType', () => {
  it('maps role text to a category', () => {
    expect(deriveDecisionMakerType('VP of Engineering')).toBe('TECHNICAL');
    expect(deriveDecisionMakerType('CIO')).toBe('TECHNICAL');
    expect(deriveDecisionMakerType('Delivery Head')).toBe('DELIVERY');
    expect(deriveDecisionMakerType('Procurement Head')).toBe('PROCUREMENT');
    expect(deriveDecisionMakerType('Vendor Manager')).toBe('VENDOR');
    expect(deriveDecisionMakerType('Talent Acquisition Head')).toBe('HR');
    expect(deriveDecisionMakerType('CFO')).toBe('BUSINESS');
  });
});

describe('relevanceBand', () => {
  it('bands relevance', () => {
    expect(relevanceBand(85)).toBe('HIGH');
    expect(relevanceBand(70)).toBe('MEDIUM');
    expect(relevanceBand(40)).toBe('LOW');
  });
});

describe('mapLeadToContactRecommendations', () => {
  it('derives one recommendation from a role, never fabricating a person', () => {
    const [rec] = mapLeadToContactRecommendations(makeLead({ id: 1, company_name: 'NorthStar' }), NOW);
    expect(rec.role).toBe('VP of Engineering');
    expect(rec.decisionMakerType).toBe('TECHNICAL');
    expect(rec.relevance).toBe(88); // reuses lead score
    expect(rec.confidence).toBe('HIGH');
    expect(rec.personName).toBeNull(); // role, not person
    expect(rec.reason).toBeNull(); // POC reason not persisted
    expect(rec.recommendedAction).toBe('Engage leadership.');
  });

  it('yields no recommendation when there is no recommended role', () => {
    expect(mapLeadToContactRecommendations(makeLead({ id: 2, company_name: 'NEC', poc_title: null }), NOW)).toHaveLength(0);
  });
});

describe('mapLeadsToContacts (dedupe)', () => {
  it('de-duplicates the same role for the same company, keeping highest relevance', () => {
    const recs = mapLeadsToContacts(
      [
        makeLead({ id: 1, company_name: 'Acme', poc_title: 'CTO', lead_score: 60 }),
        makeLead({ id: 2, company_name: 'Acme', poc_title: 'CTO', lead_score: 90 }),
        makeLead({ id: 3, company_name: 'Acme', poc_title: 'Delivery Head', lead_score: 70 }),
      ],
      NOW,
    );
    const cto = recs.filter((r) => r.role === 'CTO');
    expect(cto).toHaveLength(1);
    expect(cto[0].relevance).toBe(90);
    expect(recs).toHaveLength(2); // CTO + Delivery Head
  });
});

describe('filter/sort/aggregate', () => {
  const leads = [
    makeLead({ id: 1, company_name: 'Alpha', poc_title: 'VP of Engineering', lead_score: 90, lead_priority: 'HOT', industry: 'BFSI' }),
    makeLead({ id: 2, company_name: 'Beta', poc_title: 'Procurement Head', lead_score: 65, lead_priority: 'WARM', industry: 'Retail' }),
    makeLead({ id: 3, company_name: 'Gamma', poc_title: 'CTO', lead_score: 40, lead_priority: 'LOW', industry: 'IT' }),
  ];
  const contacts = mapLeadsToContacts(leads, NOW);

  it('filters by type, priority, minRelevance and role', () => {
    expect(filterContacts(contacts, { ...EMPTY, type: 'PROCUREMENT' })[0].company).toBe('Beta');
    expect(filterContacts(contacts, { ...EMPTY, priority: 'HOT' })).toHaveLength(1);
    expect(filterContacts(contacts, { ...EMPTY, minRelevance: '80' })).toHaveLength(1);
    expect(filterContacts(contacts, { ...EMPTY, role: 'cto' })[0].company).toBe('Gamma');
  });

  it('sorts by relevance descending by default', () => {
    expect(sortContacts(contacts, 'relevance').map((c) => c.company)).toEqual(['Alpha', 'Beta', 'Gamma']);
  });

  it('summarizes recommendations', () => {
    const s = buildContactSummary(contacts);
    expect(s.total).toBe(3);
    expect(s.highRelevance).toBe(1); // Alpha 90
    expect(s.technical).toBe(2); // VP Eng + CTO
    expect(s.procurementVendor).toBe(1); // Procurement Head
  });

  it('builds top target roles with average relevance', () => {
    const top = buildTopTargetRoles(contacts);
    const vp = top.find((r) => r.role === 'VP of Engineering');
    expect(vp?.count).toBe(1);
    expect(vp?.avgRelevance).toBe(90);
  });

  it('groups by company with primary first', () => {
    const groups = groupByCompany(
      mapLeadsToContacts(
        [
          makeLead({ id: 1, company_name: 'Acme', poc_title: 'Delivery Head', lead_score: 70 }),
          makeLead({ id: 2, company_name: 'Acme', poc_title: 'CTO', lead_score: 95 }),
        ],
        NOW,
      ),
    );
    expect(groups[0].company).toBe('Acme');
    expect(groups[0].recommendations[0].role).toBe('CTO'); // highest relevance is primary
  });
});
