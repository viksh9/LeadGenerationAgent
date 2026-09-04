import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { LeadsPage } from './LeadsPage';
import { AppRoutes } from '@/routes/AppRoutes';
import type { Lead, LeadListResponse } from '@/types/lead';

vi.mock('@/services/leads', () => ({
  getLeads: vi.fn(),
  getLead: vi.fn(),
  updateLead: vi.fn(),
  deleteLead: vi.fn(),
}));
import { getLead, getLeads } from '@/services/leads';
const getLeadsMock = vi.mocked(getLeads);
const getLeadMock = vi.mocked(getLead);

function makeLead(p: Partial<Lead> & Pick<Lead, 'id' | 'company_name'>): Lead {
  return {
    industry: 'IT',
    location: 'Pune',
    company_size: null,
    company_website: null,
    signal_type: 'HIRING',
    signal_title: 'Engineering Expansion',
    signal_description: null,
    signal_date: '2026-09-01T00:00:00Z',
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
    lead_score: 72,
    lead_priority: 'WARM',
    opportunity_summary: null,
    recommended_action: null,
    recommended_pitch: null,
    status: 'NEW',
    created_at: '2026-08-30T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    last_verified_at: null,
    ...p,
  };
}

function response(items: Lead[], overrides: Partial<LeadListResponse> = {}): LeadListResponse {
  return { items, total: items.length, page: 1, page_size: 20, total_pages: 1, ...overrides };
}

const LEADS = [
  makeLead({ id: 1, company_name: 'NorthStar Banking', lead_priority: 'HOT', lead_score: 94 }),
  makeLead({ id: 2, company_name: 'ABC Technologies', lead_priority: 'WARM', lead_score: 66 }),
];

beforeEach(() => getLeadsMock.mockReset());
afterEach(() => vi.clearAllMocks());

describe('LeadsPage', () => {
  it('renders leads in a table', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    expect(await screen.findByText('NorthStar Banking')).toBeInTheDocument();
    expect(screen.getByText('ABC Technologies')).toBeInTheDocument();
  });

  it('shows a loading skeleton then a total count', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS, { total: 2 }));
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    expect(await screen.findByText(/2 leads/i)).toBeInTheDocument();
  });

  it('shows an error state with retry', async () => {
    // Only the first call errors; any stray call resolves so no rejected promise
    // lingers across tests.
    getLeadsMock.mockResolvedValue(response([]));
    getLeadsMock.mockRejectedValueOnce(new Error('boom'));
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    expect(await screen.findByText(/unable to load leads/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('shows an empty state', async () => {
    getLeadsMock.mockResolvedValue(response([]));
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    expect(await screen.findByText(/no leads found/i)).toBeInTheDocument();
  });

  it('applies a priority filter to the query', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    await screen.findByText('NorthStar Banking');

    await userEvent.selectOptions(screen.getByLabelText('Priority'), 'HOT');
    await waitFor(() =>
      expect(getLeadsMock).toHaveBeenCalledWith(expect.objectContaining({ lead_priority: 'HOT' })),
    );
  });

  it('initializes filters from the URL (deep link)', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderWithProviders(<LeadsPage />, { route: '/leads?lead_priority=HOT' });
    await waitFor(() =>
      expect(getLeadsMock).toHaveBeenCalledWith(expect.objectContaining({ lead_priority: 'HOT' })),
    );
    expect((screen.getByLabelText('Priority') as HTMLSelectElement).value).toBe('HOT');
  });

  it('debounces search into the query', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    await screen.findByText('NorthStar Banking');

    await userEvent.type(screen.getByLabelText('Search'), 'banking');
    await waitFor(
      () =>
        expect(getLeadsMock).toHaveBeenCalledWith(expect.objectContaining({ search: 'banking' })),
      { timeout: 2000 },
    );
  });

  it('sorts when a column header is clicked', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    await screen.findByText('NorthStar Banking');

    await userEvent.click(screen.getByRole('button', { name: /sort by company/i }));
    await waitFor(() =>
      expect(getLeadsMock).toHaveBeenCalledWith(expect.objectContaining({ sort_by: 'company_name' })),
    );
  });

  it('paginates to the next page', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS, { total: 40, total_pages: 2, page: 1 }));
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    await screen.findByText('NorthStar Banking');

    await userEvent.click(screen.getByRole('button', { name: /next page/i }));
    await waitFor(() =>
      expect(getLeadsMock).toHaveBeenCalledWith(expect.objectContaining({ page: 2 })),
    );
  });

  it('navigates to lead details when a row is viewed', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    getLeadMock.mockResolvedValue(LEADS[0]);
    renderWithProviders(<AppRoutes />, { route: '/leads' });

    const view = await screen.findByRole('button', { name: /view northstar banking/i });
    await userEvent.click(view);
    // Landed on the real Lead Details page.
    expect(await screen.findByRole('link', { name: /back to leads/i })).toBeInTheDocument();
  });

  it('has an accessible responsive table container', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    const { container } = renderWithProviders(<LeadsPage />, { route: '/leads' });
    await screen.findByText('NorthStar Banking');
    // Table is wrapped in a horizontally scrollable container.
    expect(container.querySelector('.overflow-x-auto')).toBeTruthy();
    expect(within(screen.getByRole('table')).getAllByRole('row').length).toBeGreaterThan(1);
  });
});
