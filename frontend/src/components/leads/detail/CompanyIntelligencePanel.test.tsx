import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';

import { renderWithProviders } from '@/test/test-utils';
import { CompanyIntelligencePanel } from './CompanyIntelligencePanel';

vi.mock('@/services/intelligence', async (importActual) => {
  const actual = await importActual<typeof import('@/services/intelligence')>();
  return { ...actual, fetchLeadIntelligence: vi.fn() };
});

import { fetchLeadIntelligence, type LeadIntelligence } from '@/services/intelligence';

const mockIntel = vi.mocked(fetchLeadIntelligence);

const base = (over: Partial<LeadIntelligence> = {}): LeadIntelligence => ({
  lead_id: 1, company_id: 2, company_name: 'Acme Tech', lead_score: 85, lead_priority: 'HOT',
  data_trust: 82, contact_trust: 0, signal_summary: '',
  company_profile: { company_name: 'Acme Tech', industry: 'IT Services', india_presence: 'Yes',
    india_entity_type: null, website: 'https://acme.example-real.in', primary_location: 'Bengaluru, Karnataka',
    registered_location: null, career_site: 'https://acme.example-real.in/careers', technology_focus: [],
    current_hiring_signal: null, opportunity: 'Staff Augmentation', data_trust: 82, headline: 'Acme Tech' },
  opportunity: { opportunity_type: 'STAFF_AUGMENTATION', label: 'Staff Augmentation', staffing_need: 'HIGH',
    estimated_team: null, urgency: 'HIGH', technologies: [], signals: [] },
  recommended_roles: [], recommendation_confidence: 0, primary_poc: null, secondary_pocs: [],
  ai_highlights: { highlights: [], ai_available: false, ai_insight: null, model_version: null, generated_at: null },
  sources: [
    { field: 'website_url', value: 'https://acme.example-real.in', source: 'Official Company Website',
      source_type: 'company_website', source_url: 'https://acme.example-real.in', source_record_id: null,
      trust_score: 100, verification_status: null, evidence: null, retrieved_at: null, last_verified_at: null },
  ],
  freshness_score: 0, freshness_status: 'UNKNOWN', sales_action: '', generated_at: null,
  ...over,
});

describe('CompanyIntelligencePanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows identity + website with a source badge, and distinct address labels', async () => {
    mockIntel.mockResolvedValue(base());
    renderWithProviders(<CompanyIntelligencePanel leadId={1} />);
    expect(await screen.findByText('IT Services')).toBeInTheDocument();
    expect(screen.getByText('Official Company Website')).toBeInTheDocument();   // source badge
    expect(screen.getByText('Operating address')).toBeInTheDocument();
    expect(screen.getByText('Registered address')).toBeInTheDocument();
  });

  it('shows honest empty states when data is missing (no fabrication)', async () => {
    mockIntel.mockResolvedValue(base());
    renderWithProviders(<CompanyIntelligencePanel leadId={1} />);
    // No registered address in the fixture -> honest empty state.
    expect(await screen.findByText('No verified registered address.')).toBeInTheDocument();
  });
});
