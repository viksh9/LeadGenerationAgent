import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes, useSearchParams } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { CompaniesPage } from './CompaniesPage';
import type { Lead, LeadListResponse } from '@/types/lead';

vi.mock('@/services/leads', () => ({ getLeads: vi.fn() }));
import { getLeads } from '@/services/leads';
const getLeadsMock = vi.mocked(getLeads);

function makeLead(p: Partial<Lead> & Pick<Lead, 'id' | 'company_name'>): Lead {
  return {
    industry: 'IT',
    location: 'Pune',
    company_size: null,
    company_website: null,
    signal_type: 'HIRING',
    signal_title: 'x',
    signal_description: null,
    signal_date: '2026-09-01T00:00:00Z',
    source_name: null,
    source_url: null,
    technologies: ['Java'],
    project_name: null,
    project_value: null,
    estimated_hiring: 10,
    hiring_roles: [],
    poc_name: null,
    poc_title: null,
    poc_linkedin_url: null,
    public_contact: null,
    signal_confidence: null,
    lead_score: 60,
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

const LEADS: Lead[] = [
  makeLead({ id: 1, company_name: 'NorthStar Banking Technologies', industry: 'BFSI', lead_score: 90, lead_priority: 'HOT' }),
  makeLead({ id: 2, company_name: 'NorthStar Banking Technologies', industry: 'BFSI', lead_score: 60, lead_priority: 'WARM' }),
  makeLead({ id: 3, company_name: 'Helios Health', industry: 'Healthcare', lead_score: 70, lead_priority: 'WARM' }),
];

function response(items: Lead[]): LeadListResponse {
  return { items, total: items.length, page: 1, page_size: 100, total_pages: 1 };
}

function LeadsStub() {
  const [sp] = useSearchParams();
  return <div>Leads for {sp.get('search')}</div>;
}

function renderCompanies() {
  return renderWithProviders(
    <Routes>
      <Route path="/companies" element={<CompaniesPage />} />
      <Route path="/leads" element={<LeadsStub />} />
    </Routes>,
    { route: '/companies' },
  );
}

beforeEach(() => getLeadsMock.mockReset());
afterEach(() => vi.clearAllMocks());

describe('CompaniesPage', () => {
  it('aggregates leads into unique companies', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderCompanies();

    expect(await screen.findByText('NorthStar Banking Technologies')).toBeInTheDocument();
    expect(screen.getByText('Helios Health')).toBeInTheDocument();
    // 3 leads across 2 companies -> 2 data rows + 1 header row.
    const table = screen.getByRole('table');
    expect(within(table).getAllByRole('row')).toHaveLength(3);
    // 2 companies subtitle
    expect(screen.getByText(/2 companies across 3 leads/i)).toBeInTheDocument();
  });

  it('filters companies by search', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderCompanies();
    await screen.findByText('NorthStar Banking Technologies');

    await userEvent.type(screen.getByLabelText('Search'), 'helios');
    expect(screen.getByText('Helios Health')).toBeInTheDocument();
    expect(screen.queryByText('NorthStar Banking Technologies')).not.toBeInTheDocument();
  });

  it('sorts by company name', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderCompanies();
    await screen.findByText('NorthStar Banking Technologies');

    await userEvent.selectOptions(screen.getByLabelText('Sort by'), 'name');
    const rows = within(screen.getByRole('table')).getAllByRole('row');
    // First data row (index 1) should be Helios (alphabetical).
    expect(within(rows[1]).getByText('Helios Health')).toBeInTheDocument();
  });

  it('shows a loading skeleton', async () => {
    let resolve!: (value: LeadListResponse) => void;
    getLeadsMock.mockReturnValue(new Promise<LeadListResponse>((r) => (resolve = r)));
    renderCompanies();
    expect(screen.getByTestId('companies-skeleton')).toBeInTheDocument();
    // Settle so no pending promise dangles into the next test.
    resolve(response([]));
    await screen.findByText(/no companies yet/i);
  });

  it('shows an error state', async () => {
    getLeadsMock.mockResolvedValue(response([]));
    getLeadsMock.mockRejectedValueOnce(new Error('boom'));
    renderCompanies();
    expect(await screen.findByText(/unable to load companies/i)).toBeInTheDocument();
  });

  it('shows an empty state', async () => {
    getLeadsMock.mockResolvedValue(response([]));
    renderCompanies();
    expect(await screen.findByText(/no companies yet/i)).toBeInTheDocument();
  });

  it('navigates to leads filtered by the company', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderCompanies();
    await screen.findByText('NorthStar Banking Technologies');

    await userEvent.click(
      screen.getByRole('button', { name: /view leads for northstar banking technologies/i }),
    );
    expect(await screen.findByText('Leads for NorthStar Banking Technologies')).toBeInTheDocument();
  });
});
