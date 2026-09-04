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

function makeLead(p: Partial<Lead> = {}): Lead {
  return {
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
});
afterEach(() => vi.clearAllMocks());

describe('LeadDetailsPage', () => {
  it('renders full lead intelligence', async () => {
    getLeadMock.mockResolvedValue(makeLead());
    renderDetail();

    expect(await screen.findByRole('heading', { level: 2, name: /northstar banking technologies/i })).toBeInTheDocument();
    expect(screen.getAllByText('88').length).toBeGreaterThan(0); // score (header + indicator)
    expect(screen.getByText('HOT')).toBeInTheDocument();
    expect(screen.getByText('Large-scale, project-driven capacity ramp-up.')).toBeInTheDocument();
    expect(screen.getByText('Java')).toBeInTheDocument();
    expect(screen.getByText('Priya Raman')).toBeInTheDocument();
    expect(screen.getByText(/we noticed/i)).toBeInTheDocument(); // pitch
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

  it('deletes the lead and navigates back to the list', async () => {
    getLeadMock.mockResolvedValue(makeLead());
    deleteLeadMock.mockResolvedValue(undefined);
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderDetail();
    await screen.findByRole('heading', { level: 2, name: /northstar/i });

    await userEvent.click(screen.getByRole('button', { name: /delete/i }));
    await waitFor(() => expect(deleteLeadMock).toHaveBeenCalledWith(1));
    expect(await screen.findByText('Leads list page')).toBeInTheDocument();
    confirmSpy.mockRestore();
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
});
