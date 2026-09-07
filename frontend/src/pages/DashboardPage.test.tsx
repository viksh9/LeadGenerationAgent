import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { DashboardPage } from './DashboardPage';
import { AppRoutes } from '@/routes/AppRoutes';
import type { Lead, LeadListResponse } from '@/types/lead';

// Mock the API service — tests never touch a real backend.
vi.mock('@/services/leads', () => ({
  getLeads: vi.fn(),
  getLead: vi.fn(),
  updateLead: vi.fn(),
  deleteLead: vi.fn(),
}));
import { getLead, getLeads } from '@/services/leads';
const getLeadsMock = vi.mocked(getLeads);
const getLeadMock = vi.mocked(getLead);

const now = new Date();
const iso = (daysAgo: number) => new Date(now.getTime() - daysAgo * 86_400_000).toISOString();

function makeLead(partial: Partial<Lead> & Pick<Lead, 'id' | 'company_name'>): Lead {
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
    location: null,
    company_size: null,
    company_website: null,
    signal_type: 'HIRING',
    signal_title: 'Engineering Expansion',
    signal_description: null,
    signal_date: iso(1),
    source_name: null,
    source_url: null,
    technologies: [],
    project_name: null,
    project_value: null,
    estimated_hiring: null,
    hiring_roles: [],
    poc_name: null,
    poc_title: null,
    poc_linkedin_url: null,
    public_contact: null,
    signal_confidence: null,
    lead_score: 50,
    lead_priority: 'NURTURE',
    opportunity_summary: 'Opportunity',
    recommended_action: null,
    recommended_pitch: null,
    status: 'NEW',
    created_at: iso(2),
    updated_at: iso(1),
    last_verified_at: null,
    ...partial,
  };
}

const LEADS: Lead[] = [
  makeLead({
    id: 1,
    company_name: 'NorthStar Banking Technologies',
    industry: 'BFSI',
    signal_type: 'PROJECT_AWARD',
    signal_title: 'Digital Banking Transformation',
    lead_score: 94,
    lead_priority: 'HOT',
    opportunity_summary: 'Large-scale ramp-up',
    signal_date: iso(0),
  }),
  makeLead({ id: 2, company_name: 'ABC Technologies', lead_score: 88, lead_priority: 'HOT', signal_date: iso(1) }),
  makeLead({ id: 3, company_name: 'Helios Health', lead_score: 66, lead_priority: 'WARM', status: 'QUALIFIED' }),
  makeLead({ id: 4, company_name: 'Harbor Retail', lead_score: 22, lead_priority: 'LOW' }),
];

function listResponse(items: Lead[]): LeadListResponse {
  return { items, total: items.length, page: 1, page_size: 100, total_pages: 1 };
}

beforeEach(() => {
  getLeadsMock.mockReset();
});
afterEach(() => vi.clearAllMocks());

describe('DashboardPage', () => {
  it('renders the heading and KPI cards from API data', async () => {
    getLeadsMock.mockResolvedValue(listResponse(LEADS));
    renderWithProviders(<DashboardPage />, { route: '/dashboard' });

    expect(
      screen.getByRole('heading', { name: /lead intelligence dashboard/i }),
    ).toBeInTheDocument();
    // Wait for the data-driven KPI cards to render.
    expect(await screen.findByText('Total Leads')).toBeInTheDocument();
    for (const label of ['Hot Leads', 'Warm Leads', 'Qualified Opportunities']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('computes the HOT lead count', async () => {
    getLeadsMock.mockResolvedValue(listResponse(LEADS));
    renderWithProviders(<DashboardPage />, { route: '/dashboard' });

    const hotCard = (await screen.findByText('Hot Leads')).closest('div')!.parentElement!;
    expect(within(hotCard).getByText('2')).toBeInTheDocument();
  });

  it('renders top opportunities sorted by score', async () => {
    getLeadsMock.mockResolvedValue(listResponse(LEADS));
    renderWithProviders(<DashboardPage />, { route: '/dashboard' });

    const table = (await screen.findByText('Top Opportunities')).closest('div')!.parentElement!;
    expect(within(table).getByText('NorthStar Banking Technologies')).toBeInTheDocument();
    // Company-level columns are shown (not per-signal opportunity text).
    expect(within(table).getByText('IT openings')).toBeInTheDocument();
  });

  it('renders recent signals', async () => {
    getLeadsMock.mockResolvedValue(listResponse(LEADS));
    renderWithProviders(<DashboardPage />, { route: '/dashboard' });

    expect(await screen.findByText('Recent Signals')).toBeInTheDocument();
    expect(screen.getByText('Digital Banking Transformation')).toBeInTheDocument();
  });

  it('renders quick action buttons (Analyze disabled)', async () => {
    getLeadsMock.mockResolvedValue(listResponse(LEADS));
    renderWithProviders(<DashboardPage />, { route: '/dashboard' });

    expect(await screen.findByRole('button', { name: /view all leads/i })).toBeEnabled();
    expect(screen.getByRole('button', { name: /view hot leads/i })).toBeEnabled();
    expect(screen.getByRole('button', { name: /analyze new lead/i })).toBeEnabled();
  });

  it('shows the loading skeleton while fetching', () => {
    getLeadsMock.mockReturnValue(new Promise<LeadListResponse>(() => {}));
    renderWithProviders(<DashboardPage />, { route: '/dashboard' });
    expect(screen.getByTestId('dashboard-skeleton')).toBeInTheDocument();
  });

  it('shows an error state with retry', async () => {
    getLeadsMock.mockRejectedValue({ code: 'network_error', message: 'boom' });
    renderWithProviders(<DashboardPage />, { route: '/dashboard' });
    expect(await screen.findByText(/unable to load lead intelligence/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('shows an empty state when there are no leads', async () => {
    getLeadsMock.mockResolvedValue(listResponse([]));
    renderWithProviders(<DashboardPage />, { route: '/dashboard' });
    expect(await screen.findByText(/no verified indian it signals available yet/i)).toBeInTheDocument();
  });

  it('shows a demo-data banner when all leads are synthetic', async () => {
    const demo = LEADS.map((l) => makeLead({ ...l, data_provenance: 'SYNTHETIC' }));
    getLeadsMock.mockResolvedValue(listResponse(demo));
    renderWithProviders(<DashboardPage />, { route: '/dashboard' });
    expect(await screen.findByText(/demo data — no real sources connected yet/i)).toBeInTheDocument();
  });

  it('does not show the demo banner for real leads', async () => {
    getLeadsMock.mockResolvedValue(listResponse(LEADS));
    renderWithProviders(<DashboardPage />, { route: '/dashboard' });
    await screen.findByText('Total Leads');
    expect(screen.queryByText(/demo data/i)).not.toBeInTheDocument();
  });

  it('navigates to lead details when a top opportunity is viewed', async () => {
    getLeadsMock.mockResolvedValue(listResponse(LEADS));
    getLeadMock.mockResolvedValue(LEADS[0]);
    renderWithProviders(<AppRoutes />, { route: '/dashboard' });

    const viewButton = await screen.findByRole('button', {
      name: /view northstar banking technologies/i,
    });
    await userEvent.click(viewButton);

    // The Lead Details page is now the real page; confirm we landed there.
    expect(await screen.findByRole('link', { name: /back to leads/i })).toBeInTheDocument();
  });
});
