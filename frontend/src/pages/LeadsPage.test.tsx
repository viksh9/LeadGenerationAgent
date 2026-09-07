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
import { deleteLead, getLead, getLeads, updateLead } from '@/services/leads';
const getLeadsMock = vi.mocked(getLeads);
const getLeadMock = vi.mocked(getLead);
const updateLeadMock = vi.mocked(updateLead);
const deleteLeadMock = vi.mocked(deleteLead);

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
    expect(await screen.findByText(/no leads yet/i)).toBeInTheDocument();
  });

  it('applies a priority filter to the query', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    await screen.findByText('NorthStar Banking');

    await userEvent.selectOptions(screen.getByLabelText('Priority'), 'HOT');
    await waitFor(() =>
      expect(getLeadsMock).toHaveBeenCalledWith(expect.objectContaining({ lead_priority: 'HOT' }), expect.anything()),
    );
  });

  it('initializes filters from the URL (deep link)', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderWithProviders(<LeadsPage />, { route: '/leads?lead_priority=HOT' });
    await waitFor(() =>
      expect(getLeadsMock).toHaveBeenCalledWith(expect.objectContaining({ lead_priority: 'HOT' }), expect.anything()),
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
        expect(getLeadsMock).toHaveBeenCalledWith(expect.objectContaining({ search: 'banking' }), expect.anything()),
      { timeout: 2000 },
    );
  });

  it('sorts when a column header is clicked', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    await screen.findByText('NorthStar Banking');

    await userEvent.click(screen.getByRole('button', { name: /sort by company/i }));
    await waitFor(() =>
      expect(getLeadsMock).toHaveBeenCalledWith(expect.objectContaining({ sort_by: 'company_name' }), expect.anything()),
    );
  });

  it('paginates to the next page', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS, { total: 40, total_pages: 2, page: 1 }));
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    await screen.findByText('NorthStar Banking');

    await userEvent.click(screen.getByRole('button', { name: /next page/i }));
    await waitFor(() =>
      expect(getLeadsMock).toHaveBeenCalledWith(expect.objectContaining({ page: 2 }), expect.anything()),
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

  it('applies an industry filter to the query', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    await screen.findByText('NorthStar Banking');

    await userEvent.selectOptions(screen.getByLabelText('Industry'), 'BFSI');
    await waitFor(() =>
      expect(getLeadsMock).toHaveBeenCalledWith(expect.objectContaining({ industry: 'BFSI' }), expect.anything()),
    );
  });

  it('applies a status filter to the query', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    await screen.findByText('NorthStar Banking');

    await userEvent.selectOptions(screen.getByLabelText('Status'), 'CONTACTED');
    await waitFor(() =>
      expect(getLeadsMock).toHaveBeenCalledWith(expect.objectContaining({ status: 'CONTACTED' }), expect.anything()),
    );
  });

  it('applies a signal-type filter to the query', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    await screen.findByText('NorthStar Banking');

    await userEvent.selectOptions(screen.getByLabelText('Signal type'), 'PROJECT_AWARD');
    await waitFor(() =>
      expect(getLeadsMock).toHaveBeenCalledWith(
        expect.objectContaining({ signal_type: 'PROJECT_AWARD' }),
        expect.anything(),
      ),
    );
  });

  it('applies a minimum-score filter to the query', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    await screen.findByText('NorthStar Banking');

    await userEvent.type(screen.getByLabelText('Min score'), '80');
    await waitFor(() =>
      expect(getLeadsMock).toHaveBeenCalledWith(expect.objectContaining({ min_score: 80 }), expect.anything()),
    );
  });

  it('humanizes signal enums and shows extra technologies', async () => {
    getLeadsMock.mockResolvedValue(
      response([
        makeLead({
          id: 9,
          company_name: 'Helios Systems',
          signal_type: 'PROJECT_AWARD',
          technologies: ['Java', 'AWS', 'React', 'Kafka'],
          opportunity_summary: 'Large-scale ramp-up',
        }),
      ]),
    );
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    // Scope to the lead's row — "Project Award" also appears as a filter option.
    await screen.findByText('Helios Systems');
    const row = screen.getByText('Helios Systems').closest('tr') as HTMLElement;
    expect(within(row).getByText('Project Award')).toBeInTheDocument();
    expect(within(row).getByText('+2 more')).toBeInTheDocument();
    expect(within(row).getByText('Large-scale ramp-up')).toBeInTheDocument();
    expect(screen.queryByText('PROJECT_AWARD')).not.toBeInTheDocument();
  });

  it('renders active filter chips and removes one', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderWithProviders(<LeadsPage />, { route: '/leads?lead_priority=HOT&industry=BFSI' });
    await screen.findByText('NorthStar Banking');

    expect(screen.getByText('Priority: HOT')).toBeInTheDocument();
    expect(screen.getByText('Industry: BFSI')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /remove filter priority: hot/i }));
    await waitFor(() => expect(screen.queryByText('Priority: HOT')).not.toBeInTheDocument());
    // The other chip survives.
    expect(screen.getByText('Industry: BFSI')).toBeInTheDocument();
  });

  it('clears all filters from the chip bar', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderWithProviders(<LeadsPage />, { route: '/leads?lead_priority=HOT&status=NEW' });
    await screen.findByText('NorthStar Banking');

    await userEvent.click(screen.getByRole('button', { name: /clear all/i }));
    await waitFor(() => expect(screen.queryByText('Priority: HOT')).not.toBeInTheDocument());
    expect(screen.queryByText('Status: NEW')).not.toBeInTheDocument();
  });

  it('shows a no-results state when filters match nothing', async () => {
    getLeadsMock.mockResolvedValue(response([]));
    renderWithProviders(<LeadsPage />, { route: '/leads?lead_priority=HOT' });
    expect(await screen.findByText(/no leads match your current filters/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /clear filters/i })).toBeInTheDocument();
  });

  it('updates lead status via the inline select', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    updateLeadMock.mockResolvedValue({ ...LEADS[0], status: 'CONTACTED' });
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    await screen.findByText('NorthStar Banking');

    await userEvent.selectOptions(
      screen.getByLabelText('Status for NorthStar Banking'),
      'CONTACTED',
    );
    await waitFor(() =>
      expect(updateLeadMock).toHaveBeenCalledWith(1, { status: 'CONTACTED' }),
    );
  });

  it('deletes a lead only after confirmation', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    deleteLeadMock.mockResolvedValue(undefined);
    renderWithProviders(<LeadsPage />, { route: '/leads' });
    await screen.findByText('NorthStar Banking');

    // Opening the menu must NOT delete on its own.
    await userEvent.click(screen.getByRole('button', { name: /delete northstar banking/i }));
    expect(deleteLeadMock).not.toHaveBeenCalled();
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(deleteLeadMock).toHaveBeenCalledWith(1));
  });

  it('navigates to the analyze flow from the header action', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderWithProviders(<AppRoutes />, { route: '/leads' });
    await screen.findByText('NorthStar Banking');

    await userEvent.click(screen.getByRole('link', { name: /analyze new lead/i }));
    expect(await screen.findByRole('heading', { name: /analyze a lead/i })).toBeInTheDocument();
  });
});
