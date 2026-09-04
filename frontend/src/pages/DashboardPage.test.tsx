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
}));
import { getLeads } from '@/services/leads';
const getLeadsMock = vi.mocked(getLeads);

const now = new Date();
const iso = (daysAgo: number) => new Date(now.getTime() - daysAgo * 86_400_000).toISOString();

function makeLead(partial: Partial<Lead> & Pick<Lead, 'id' | 'company_name'>): Lead {
  return {
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
    expect(within(table).getByText('Large-scale ramp-up')).toBeInTheDocument();
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
    expect(screen.getByRole('button', { name: /analyze new lead/i })).toBeDisabled();
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
    expect(await screen.findByText(/no leads available yet/i)).toBeInTheDocument();
  });

  it('navigates to lead details when a top opportunity is viewed', async () => {
    getLeadsMock.mockResolvedValue(listResponse(LEADS));
    renderWithProviders(<AppRoutes />, { route: '/dashboard' });

    const viewButton = await screen.findByRole('button', {
      name: /view northstar banking technologies/i,
    });
    await userEvent.click(viewButton);

    expect(
      await screen.findByRole('heading', { level: 2, name: /lead #1/i }),
    ).toBeInTheDocument();
  });
});
