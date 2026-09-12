import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';

import { renderWithProviders } from '@/test/test-utils';
import { AIProfileHighlightsPanel } from './AIProfileHighlightsPanel';

vi.mock('@/services/intelligence', async (importActual) => {
  const actual = await importActual<typeof import('@/services/intelligence')>();
  return { ...actual, fetchLeadIntelligence: vi.fn(), fetchLeadSources: vi.fn(), refreshLeadIntelligence: vi.fn() };
});

import { fetchLeadIntelligence, type LeadIntelligence } from '@/services/intelligence';

const mockIntel = vi.mocked(fetchLeadIntelligence);

const intel = (over: Partial<LeadIntelligence> = {}): LeadIntelligence => ({
  lead_id: 1, company_id: 2, company_name: 'Acme Tech', lead_score: 85, lead_priority: 'HOT',
  data_trust: 82, contact_trust: 70, signal_summary: 'High technology hiring — 47 open IT roles',
  company_profile: { company_name: 'Acme Tech', industry: 'IT Services', india_presence: 'Yes',
    india_entity_type: null, website: null, primary_location: 'Bengaluru', registered_location: null,
    career_site: null, technology_focus: ['Java'], current_hiring_signal: null, opportunity: 'Staff Augmentation',
    data_trust: 82, headline: 'Acme Tech (IT Services)' },
  opportunity: { opportunity_type: 'STAFF_AUGMENTATION', label: 'Staff Augmentation', staffing_need: 'HIGH',
    estimated_team: 47, urgency: 'HIGH', technologies: ['Java'], signals: ['HIRING'] },
  recommended_roles: [], recommendation_confidence: 80,
  primary_poc: { poc: { id: 9, full_name: 'Jane Doe', job_title: 'VP Engineering' } as never,
    poc_status: 'LIKELY', role_match_score: 92, contact_trust_score: 70, contact_trust_status: 'LIKELY', is_primary: true },
  secondary_pocs: [],
  ai_highlights: { highlights: [
    { highlight_title: 'Hiring Trend', highlight_text: 'High', trust_level: 'HIGH', supporting_signal_ids: [], supporting_source_ids: [], ai_generated: false },
    { highlight_title: 'Technology Focus', highlight_text: 'Java • AWS', trust_level: 'HIGH', supporting_signal_ids: [], supporting_source_ids: [], ai_generated: false },
  ], ai_available: false, ai_insight: null, model_version: null, generated_at: null },
  sources: [{ field: 'signal', value: null, source: 'Official Career Site', source_type: null, source_url: null,
    source_record_id: null, trust_score: 0, verification_status: null, evidence: null, retrieved_at: null, last_verified_at: null }],
  freshness_score: 95, freshness_status: 'FRESH', sales_action: 'Recommended outreach to VP Engineering', generated_at: null,
  ...over,
});

describe('AIProfileHighlightsPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders deterministic highlights + distinct trust scores and the contributing source', async () => {
    mockIntel.mockResolvedValue(intel());
    renderWithProviders(<AIProfileHighlightsPanel leadId={1} />);
    expect(await screen.findByText('Data Trust 82%')).toBeInTheDocument();
    expect(screen.getByText('Contact Trust 70%')).toBeInTheDocument();
    expect(screen.getByText('Hiring Trend')).toBeInTheDocument();
    expect(screen.getByText('Official Career Site')).toBeInTheDocument();
  });

  it('shows "AI Profile Highlights unavailable" when AI is not available (no fake fallback)', async () => {
    mockIntel.mockResolvedValue(intel());
    renderWithProviders(<AIProfileHighlightsPanel leadId={1} />);
    expect(await screen.findByText('AI Profile Highlights unavailable.')).toBeInTheDocument();
  });

  it('shows the AI insight text when AI is available', async () => {
    mockIntel.mockResolvedValue(intel({ ai_highlights: {
      highlights: [], ai_available: true, ai_insight: 'Strong engineering hiring activity.',
      model_version: 'test-model', generated_at: null } }));
    renderWithProviders(<AIProfileHighlightsPanel leadId={1} />);
    expect(await screen.findByText('Strong engineering hiring activity.')).toBeInTheDocument();
  });
});
