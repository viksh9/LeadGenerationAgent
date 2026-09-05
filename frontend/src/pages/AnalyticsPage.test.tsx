import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { AnalyticsPage } from './AnalyticsPage';
import type { Lead, LeadListResponse } from '@/types/lead';

vi.mock('@/services/leads', () => ({ getLeads: vi.fn() }));
import { getLeads } from '@/services/leads';
const getLeadsMock = vi.mocked(getLeads);

const FIXED_NOW = Date.parse('2026-09-30T00:00:00Z');

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

const LEADS: Lead[] = [
  makeLead({ id: 1, company_name: 'Alpha', industry: 'BFSI', lead_priority: 'HOT', lead_score: 90, signal_type: 'PROJECT_AWARD', estimated_hiring: 40, status: 'QUALIFIED', technologies: ['Java', 'AWS'] }),
  makeLead({ id: 2, company_name: 'Beta', industry: 'BFSI', lead_priority: 'WARM', lead_score: 60 }),
  makeLead({ id: 3, company_name: 'Gamma', industry: 'Healthcare', lead_priority: 'LOW', lead_score: 20, signal_date: '2026-08-01T00:00:00Z' }),
];

function response(items: Lead[]): LeadListResponse {
  return { items, total: items.length, page: 1, page_size: 100, total_pages: 1 };
}

function renderPage(route = '/analytics') {
  return renderWithProviders(
    <Routes>
      <Route path="/analytics" element={<AnalyticsPage />} />
      <Route path="/leads" element={<div>Leads list page</div>} />
      <Route path="/leads/:id" element={<div>Lead detail page</div>} />
    </Routes>,
    { route },
  );
}

const totalCard = () => screen.getByText('Total leads').closest('.card') as HTMLElement;

let nowSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  getLeadsMock.mockReset();
  nowSpy = vi.spyOn(Date, 'now').mockReturnValue(FIXED_NOW);
});
afterEach(() => {
  nowSpy.mockRestore();
  vi.clearAllMocks();
});

describe('AnalyticsPage', () => {
  it('renders KPIs and distribution sections', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByText('Total leads');

    expect(within(totalCard()).getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Lead priority distribution')).toBeInTheDocument();
    expect(screen.getByText('Business signal distribution')).toBeInTheDocument();
    expect(screen.getByText('Lead status distribution')).toBeInTheDocument(); // not "conversion"
  });

  it('renders the industry and technology tables', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByText('Total leads');

    const industry = screen.getByText('Industry & opportunity insight').closest('.card') as HTMLElement;
    expect(within(industry).getByText('BFSI')).toBeInTheDocument();
    const tech = screen.getByText('Technology demand').closest('.card') as HTMLElement;
    expect(within(tech).getByText('Java')).toBeInTheDocument();
  });

  it('shows outreach readiness derived from leads', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByText('Total leads');
    const readiness = screen.getByText('Outreach readiness').closest('.card') as HTMLElement;
    expect(within(readiness).getByText('Ready for outreach')).toBeInTheDocument();
  });

  it('navigates to a lead from top opportunities', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByText('Total leads');

    const top = screen.getByText('Top opportunities').closest('.card') as HTMLElement;
    await userEvent.click(within(top).getByRole('button', { name: /view lead 1 for alpha/i }));
    expect(await screen.findByText('Lead detail page')).toBeInTheDocument();
  });

  it('filters by priority and recomputes the KPIs', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByText('Total leads');

    await userEvent.selectOptions(screen.getByLabelText('Priority'), 'HOT');
    await waitFor(() => expect(within(totalCard()).getByText('1')).toBeInTheDocument());
    expect(screen.getByText('Priority: HOT')).toBeInTheDocument();
  });

  it('filters by date range', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByText('Total leads');

    await userEvent.selectOptions(screen.getByLabelText('Date range'), '7d');
    // Gamma (Aug 1) falls outside the last 7 days -> 2 leads remain.
    await waitFor(() => expect(within(totalCard()).getByText('2')).toBeInTheDocument());
  });

  it('clears filters', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage('/analytics?priority=HOT');
    await screen.findByText('Total leads');
    expect(within(totalCard()).getByText('1')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /clear all/i }));
    await waitFor(() => expect(within(totalCard()).getByText('3')).toBeInTheDocument());
  });

  it('offers a CSV export action', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByText('Total leads');
    expect(screen.getByRole('button', { name: /export analytics as csv/i })).toBeEnabled();
  });

  it('shows a loading skeleton', async () => {
    let resolve!: (value: LeadListResponse) => void;
    getLeadsMock.mockReturnValue(new Promise<LeadListResponse>((r) => (resolve = r)));
    renderPage();
    expect(screen.getByTestId('analytics-skeleton')).toBeInTheDocument();
    resolve(response(LEADS));
    await screen.findByText('Total leads');
  });

  it('shows an error state', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    getLeadsMock.mockRejectedValueOnce(new Error('boom'));
    renderPage();
    expect(await screen.findByText(/unable to load analytics/i)).toBeInTheDocument();
  });

  it('shows an empty state when there are no leads', async () => {
    getLeadsMock.mockResolvedValue(response([]));
    renderPage();
    expect(await screen.findByText(/no analytics available yet/i)).toBeInTheDocument();
  });
});
