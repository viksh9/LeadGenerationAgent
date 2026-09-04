import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { AnalyzeLeadPage } from './AnalyzeLeadPage';
import type { LeadAnalysis } from '@/types/lead';

vi.mock('@/services/leads', () => ({ analyzeLead: vi.fn() }));
import { analyzeLead } from '@/services/leads';
const analyzeLeadMock = vi.mocked(analyzeLead);

function makeAnalysis(p: Partial<LeadAnalysis> = {}): LeadAnalysis {
  return {
    lead_id: 7,
    company_name: 'Acme Corp',
    signal_analysis: {
      signal_types: ['HIRING', 'PROJECT_AWARD'],
      signals: [],
      signal_strength: 90,
      signal_strength_label: 'STRONG',
      detected_keywords: [],
      detected_technologies: ['Java', 'AWS'],
      estimated_hiring: 20,
      detected_roles: [],
    },
    opportunity_analysis: {
      opportunity_type: 'LARGE_SCALE_RAMP_UP',
      secondary_opportunity_types: [],
      potential_staffing_need: 'HIGH',
      likely_roles: [],
      likely_technologies: [],
      estimated_team_size_min: 20,
      estimated_team_size_max: 20,
      urgency: 'HIGH',
      business_reason: 'A ramp-up appears likely.',
      recommended_next_step: 'Identify engineering leadership.',
      opportunity_confidence: 90,
      opportunity_confidence_label: 'HIGH',
    },
    scoring_result: {
      score: 85,
      priority: 'HOT',
      score_breakdown: {
        large_technology_hiring: 15,
        new_project_or_contract: 20,
        enterprise_project: 5,
        multiple_openings: 10,
        expansion_or_transformation: 8,
        technology_match: 7,
        decision_maker: 0,
        recency: 5,
      },
      positive_signals: [],
      negative_signals: [],
      explanation: '',
      scoring_confidence: 90,
      scoring_confidence_label: 'HIGH',
    },
    poc_recommendation: {
      primary_role: { role: 'VP Engineering', role_category: 'ENGINEERING_LEADERSHIP', decision_maker_type: 'TECHNICAL', relevance_score: 95, reason: '' },
      secondary_roles: [{ role: 'CTO', role_category: 'TECHNOLOGY_LEADERSHIP', decision_maker_type: 'TECHNICAL', relevance_score: 90, reason: '' }],
      recommendation_confidence: 88,
      recommendation_confidence_label: 'HIGH',
      reason: '',
    },
    pitch_result: {
      email_subject: 'Scaling your engineering team',
      opening_message: '',
      value_proposition: '',
      recommended_pitch: 'Subject: Scaling…\n\nWe noticed your team is expanding.',
      call_to_action: '',
      linkedin_message: '',
      call_talking_points: [],
      target_role: 'VP Engineering',
      message_strategy: 'SCALE_UP',
      confidence: 90,
      confidence_label: 'HIGH',
    },
    final_score: 85,
    priority: 'HOT',
    recommended_action: 'Identify engineering leadership.',
    status: 'NEW',
    already_existed: false,
    ...p,
  };
}

function renderAnalyze() {
  return renderWithProviders(
    <Routes>
      <Route path="/leads/analyze" element={<AnalyzeLeadPage />} />
      <Route path="/leads/:id" element={<div>Lead detail stub</div>} />
    </Routes>,
    { route: '/leads/analyze' },
  );
}

beforeEach(() => analyzeLeadMock.mockReset());
afterEach(() => vi.clearAllMocks());

describe('AnalyzeLeadPage', () => {
  it('renders the form', () => {
    renderAnalyze();
    expect(screen.getByRole('heading', { level: 2, name: /analyze a lead/i })).toBeInTheDocument();
    expect(screen.getByLabelText('Company name')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /analyze lead/i })).toBeInTheDocument();
  });

  it('submits a parsed payload to analyzeLead', async () => {
    analyzeLeadMock.mockResolvedValue(makeAnalysis());
    renderAnalyze();

    await userEvent.type(screen.getByLabelText('Company name'), 'Acme Corp');
    await userEvent.type(screen.getByLabelText(/technologies/i), 'Java, AWS');
    await userEvent.type(screen.getByLabelText('Estimated hiring'), '20');
    await userEvent.click(screen.getByRole('button', { name: /analyze lead/i }));

    await waitFor(() =>
      expect(analyzeLeadMock).toHaveBeenCalledWith(
        expect.objectContaining({
          company_name: 'Acme Corp',
          technologies: ['Java', 'AWS'],
          estimated_hiring: 20,
        }),
      ),
    );
  });

  it('shows the analysis result on success', async () => {
    analyzeLeadMock.mockResolvedValue(makeAnalysis());
    renderAnalyze();

    await userEvent.type(screen.getByLabelText('Company name'), 'Acme Corp');
    await userEvent.click(screen.getByRole('button', { name: /analyze lead/i }));

    expect(await screen.findByText(/analysis complete/i)).toBeInTheDocument();
    expect(screen.getByText('HOT')).toBeInTheDocument();
    expect(screen.getByText('LARGE_SCALE_RAMP_UP')).toBeInTheDocument();
    expect(screen.getByText('VP Engineering')).toBeInTheDocument();
    expect(screen.getByText(/we noticed your team is expanding/i)).toBeInTheDocument();
  });

  it('navigates to the created lead from the result', async () => {
    analyzeLeadMock.mockResolvedValue(makeAnalysis({ lead_id: 7 }));
    renderAnalyze();

    await userEvent.type(screen.getByLabelText('Company name'), 'Acme Corp');
    await userEvent.click(screen.getByRole('button', { name: /analyze lead/i }));

    const viewLink = await screen.findByRole('link', { name: /view full lead/i });
    expect(viewLink).toHaveAttribute('href', '/leads/7');
    await userEvent.click(viewLink);
    expect(await screen.findByText('Lead detail stub')).toBeInTheDocument();
  });

  it('resets to the form with "Analyze another"', async () => {
    analyzeLeadMock.mockResolvedValue(makeAnalysis());
    renderAnalyze();

    await userEvent.type(screen.getByLabelText('Company name'), 'Acme Corp');
    await userEvent.click(screen.getByRole('button', { name: /analyze lead/i }));
    await screen.findByText(/analysis complete/i);

    await userEvent.click(screen.getByRole('button', { name: /analyze another/i }));
    expect(screen.getByLabelText('Company name')).toBeInTheDocument();
  });

  it('shows an error state on failure', async () => {
    // Only the first call errors; any stray call resolves so no rejection lingers.
    analyzeLeadMock.mockResolvedValue(makeAnalysis());
    analyzeLeadMock.mockRejectedValueOnce(new Error('boom'));
    renderAnalyze();

    await userEvent.type(screen.getByLabelText('Company name'), 'Acme Corp');
    await userEvent.click(screen.getByRole('button', { name: /analyze lead/i }));

    expect(await screen.findByText(/unable to analyze|boom/i)).toBeInTheDocument();
  });
});
