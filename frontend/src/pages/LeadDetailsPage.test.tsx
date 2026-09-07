import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { LeadDetailsPage } from './LeadDetailsPage';
import type { Lead } from '@/types/lead';

vi.mock('@/services/leads', () => ({
  getLead: vi.fn(),
  updateLead: vi.fn(),
  deleteLead: vi.fn(),
}));
import { deleteLead, getLead, updateLead } from '@/services/leads';
const getLeadMock = vi.mocked(getLead);
const updateLeadMock = vi.mocked(updateLead);
const deleteLeadMock = vi.mocked(deleteLead);

// Mock only the network fns; keep the real display helpers.
vi.mock('@/services/decisionMakers', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/decisionMakers')>();
  return { ...actual, fetchContacts: vi.fn(), fetchLeadStakeholders: vi.fn() };
});
import { fetchLeadStakeholders, type LeadStakeholders } from '@/services/decisionMakers';
const fetchLeadStakeholdersMock = vi.mocked(fetchLeadStakeholders);

function makeStakeholders(p: Partial<LeadStakeholders> = {}): LeadStakeholders {
  return {
    lead_id: 1,
    company_name: 'NorthStar Banking Technologies',
    recommendation_confidence: 70,
    recommended_roles: [
      {
        role: 'Head of Engineering',
        role_category: 'TECHNICAL',
        decision_maker_type: 'TECHNICAL',
        relevance_score: 72,
        reason: 'Owns engineering hiring decisions.',
        is_primary: true,
      },
      {
        role: 'Procurement Lead',
        role_category: 'PROCUREMENT',
        decision_maker_type: 'PROCUREMENT',
        relevance_score: 55,
        reason: null,
        is_primary: false,
      },
    ],
    verified_decision_makers: [],
    business_contacts: [],
    outreach_readiness: 'ROLE_ONLY',
    outreach_reasons: ['Only recommended roles are available so far.'],
    ...p,
  };
}

function makeLead(p: Partial<Lead> = {}): Lead {
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
    id: 1,
    company_name: 'NorthStar Banking Technologies',
    industry: 'BFSI',
    location: 'Mumbai',
    company_size: '1001-5000',
    company_website: 'https://northstar.example',
    signal_type: 'PROJECT_AWARD',
    signal_title: 'Digital Banking Transformation',
    signal_description: 'Won a modernization project and hiring engineers.',
    signal_date: '2026-09-01T00:00:00Z',
    source_name: 'press release',
    source_url: 'https://news.example/northstar',
    technologies: ['Java', 'AWS', 'DevOps'],
    project_name: 'Core Banking Revamp',
    project_value: 2500000,
    estimated_hiring: 45,
    hiring_roles: ['Java Engineer', 'AWS Engineer'],
    poc_name: 'Priya Raman',
    poc_title: 'VP of Engineering',
    poc_linkedin_url: 'https://linkedin.com/in/priya',
    public_contact: null,
    signal_confidence: 90,
    lead_score: 88,
    lead_priority: 'HOT',
    opportunity_summary: 'Large-scale, project-driven capacity ramp-up.',
    recommended_action: 'Identify engineering leadership and validate requirements.',
    recommended_pitch: 'Subject: Scaling your team\n\nWe noticed…',
    status: 'NEW',
    created_at: '2026-08-30T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    last_verified_at: null,
    ...p,
  };
}

function renderDetail(route = '/leads/1') {
  return renderWithProviders(
    <Routes>
      <Route path="/leads/:id" element={<LeadDetailsPage />} />
      <Route path="/leads" element={<div>Leads list page</div>} />
    </Routes>,
    { route },
  );
}

beforeEach(() => {
  getLeadMock.mockReset();
  updateLeadMock.mockReset();
  deleteLeadMock.mockReset();
  fetchLeadStakeholdersMock.mockReset();
  fetchLeadStakeholdersMock.mockResolvedValue(makeStakeholders());
});
afterEach(() => vi.clearAllMocks());

describe('LeadDetailsPage', () => {
  it('renders full lead intelligence', async () => {
    getLeadMock.mockResolvedValue(makeLead());
    renderDetail();

    expect(await screen.findByRole('heading', { level: 2, name: /northstar banking technologies/i })).toBeInTheDocument();
    expect(screen.getAllByText('88').length).toBeGreaterThan(0); // score (header + indicator)
    expect(screen.getAllByText('HOT').length).toBeGreaterThan(0); // header + recommendation rail
    expect(screen.getByText('Large-scale, project-driven capacity ramp-up.')).toBeInTheDocument();
    expect(screen.getByText('Java')).toBeInTheDocument();
    expect(screen.getByText('Priya Raman')).toBeInTheDocument();
    expect(screen.getByText(/we noticed/i)).toBeInTheDocument(); // pitch
  });

  it('humanizes the signal and shows a signal-strength band', async () => {
    getLeadMock.mockResolvedValue(makeLead());
    renderDetail();
    await screen.findByRole('heading', { level: 2, name: /northstar/i });

    // Enum is humanized, not shown raw.
    expect(screen.getByText('Project Award')).toBeInTheDocument();
    expect(screen.queryByText('PROJECT_AWARD')).not.toBeInTheDocument();
    // signal_confidence 90 -> STRONG band.
    expect(screen.getByText('STRONG')).toBeInTheDocument();
  });

  it('shows estimated staffing and likely roles', async () => {
    getLeadMock.mockResolvedValue(makeLead());
    renderDetail();
    await screen.findByRole('heading', { level: 2, name: /northstar/i });

    expect(screen.getByText('45 engineers')).toBeInTheDocument();
    expect(screen.getByText('Java Engineer')).toBeInTheDocument();
  });

  it('renders the evidence section', async () => {
    getLeadMock.mockResolvedValue(makeLead());
    renderDetail();
    await screen.findByRole('heading', { level: 2, name: /northstar/i });

    expect(screen.getByText('Evidence')).toBeInTheDocument();
    expect(screen.getAllByText('press release').length).toBeGreaterThan(0);
  });

  it('opens external links safely in a new tab', async () => {
    getLeadMock.mockResolvedValue(makeLead());
    renderDetail();
    await screen.findByRole('heading', { level: 2, name: /northstar/i });

    const linkedin = screen.getByRole('link', { name: /view profile/i });
    expect(linkedin).toHaveAttribute('href', 'https://linkedin.com/in/priya');
    expect(linkedin).toHaveAttribute('target', '_blank');
    expect(linkedin).toHaveAttribute('rel', expect.stringContaining('noopener'));
  });

  it('handles missing optional fields without showing null/undefined', async () => {
    getLeadMock.mockResolvedValue(
      makeLead({
        poc_name: null,
        poc_title: null,
        poc_linkedin_url: null,
        public_contact: null,
        estimated_hiring: null,
        technologies: [],
        hiring_roles: [],
      }),
    );
    renderDetail();
    await screen.findByRole('heading', { level: 2, name: /northstar/i });

    expect(screen.getByText(/no contact identified yet/i)).toBeInTheDocument();
    expect(screen.getByText(/not enough information/i)).toBeInTheDocument();
    expect(screen.queryByText(/undefined|null|NaN/)).not.toBeInTheDocument();
  });

  it('refreshes the lead by refetching', async () => {
    getLeadMock.mockResolvedValue(makeLead());
    renderDetail();
    await screen.findByRole('heading', { level: 2, name: /northstar/i });
    const callsBefore = getLeadMock.mock.calls.length;

    await userEvent.click(screen.getByRole('button', { name: /refresh lead/i }));
    await waitFor(() => expect(getLeadMock.mock.calls.length).toBeGreaterThan(callsBefore));
  });

  it('shows a loading skeleton', () => {
    getLeadMock.mockReturnValue(new Promise<Lead>(() => {}));
    renderDetail();
    expect(screen.getByTestId('lead-detail-skeleton')).toBeInTheDocument();
  });

  it('shows a not-found state for a 404', async () => {
    getLeadMock.mockResolvedValue(makeLead());
    getLeadMock.mockRejectedValueOnce({ code: 'not_found', message: 'nope', status: 404 });
    renderDetail();
    expect(await screen.findByText(/lead not found/i)).toBeInTheDocument();
  });

  it('shows a not-found state for an invalid id', () => {
    getLeadMock.mockResolvedValue(makeLead());
    renderDetail('/leads/not-a-number');
    expect(screen.getByText(/lead not found/i)).toBeInTheDocument();
  });

  it('updates the status via the API', async () => {
    getLeadMock.mockResolvedValue(makeLead());
    updateLeadMock.mockResolvedValue(makeLead({ status: 'CONTACTED' }));
    renderDetail();
    await screen.findByRole('heading', { level: 2, name: /northstar/i });

    await userEvent.selectOptions(screen.getByLabelText('Status'), 'CONTACTED');
    await waitFor(() => expect(updateLeadMock).toHaveBeenCalledWith(1, { status: 'CONTACTED' }));
  });

  it('deletes the lead only after confirmation and navigates back', async () => {
    getLeadMock.mockResolvedValue(makeLead());
    deleteLeadMock.mockResolvedValue(undefined);
    renderDetail();
    await screen.findByRole('heading', { level: 2, name: /northstar/i });

    // Triggering delete opens a confirmation dialog — it must not delete yet.
    await userEvent.click(screen.getByRole('button', { name: /delete lead/i }));
    expect(deleteLeadMock).not.toHaveBeenCalled();
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(deleteLeadMock).toHaveBeenCalledWith(1));
    expect(await screen.findByText('Leads list page')).toBeInTheDocument();
  });

  it('copies the pitch to the clipboard', async () => {
    getLeadMock.mockResolvedValue(makeLead());
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    renderDetail();
    await screen.findByRole('heading', { level: 2, name: /northstar/i });

    await userEvent.click(screen.getByRole('button', { name: /copy pitch/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining('We noticed')));
  });

  it('has a back link to the leads list', async () => {
    getLeadMock.mockResolvedValue(makeLead());
    renderDetail();
    expect(await screen.findByRole('link', { name: /back to leads/i })).toHaveAttribute('href', '/leads');
  });

  it('shows the stakeholders panel with roles, readiness and honest empty people states', async () => {
    getLeadMock.mockResolvedValue(makeLead());
    renderDetail();
    await screen.findByRole('heading', { level: 2, name: /northstar/i });

    expect(await screen.findByText('Stakeholders')).toBeInTheDocument();
    expect(screen.getByText('Head of Engineering')).toBeInTheDocument();
    expect(screen.getByText('Primary')).toBeInTheDocument();
    expect(screen.getByText('Role only')).toBeInTheDocument(); // outreach readiness
    expect(screen.getByText(/no verified people yet/i)).toBeInTheDocument();
    expect(screen.getByText(/no source-backed business contacts yet/i)).toBeInTheDocument();
  });
});
