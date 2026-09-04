import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { CompanyDetailsPage } from './CompanyDetailsPage';
import type { Lead, LeadListResponse } from '@/types/lead';

vi.mock('@/services/leads', () => ({ getLeads: vi.fn() }));
import { getLeads } from '@/services/leads';
const getLeadsMock = vi.mocked(getLeads);

function makeLead(p: Partial<Lead> & Pick<Lead, 'id' | 'company_name'>): Lead {
  return {
    industry: 'BFSI',
    location: 'Pune',
    company_size: '1001-5000',
    company_website: 'https://northstar.example',
    signal_type: 'HIRING',
    signal_title: 'Hiring 40 engineers',
    signal_description: null,
    signal_date: '2026-09-01T00:00:00Z',
    source_name: null,
    source_url: null,
    technologies: ['Java', 'AWS'],
    project_name: null,
    project_value: null,
    estimated_hiring: 40,
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

const NAME = 'NorthStar Banking Technologies';

const LEADS: Lead[] = [
  makeLead({
    id: 1,
    company_name: NAME,
    signal_type: 'PROJECT_AWARD',
    signal_title: 'Core banking modernization',
    technologies: ['Java', 'AWS'],
    lead_score: 92,
    lead_priority: 'HOT',
    estimated_hiring: 40,
    poc_name: 'Priya Raman',
    poc_title: 'VP of Engineering',
    poc_linkedin_url: 'https://linkedin.com/in/priya-example',
  }),
  makeLead({
    id: 2,
    company_name: NAME,
    signal_type: 'HIRING',
    technologies: ['Java', 'React'],
    lead_score: 60,
    lead_priority: 'WARM',
    estimated_hiring: 15,
  }),
  // Coincidental fuzzy-search hit for a different company — must be filtered out.
  makeLead({ id: 3, company_name: 'Other Corp', lead_score: 99, lead_priority: 'HOT' }),
];

function response(items: Lead[]): LeadListResponse {
  return { items, total: items.length, page: 1, page_size: 100, total_pages: 1 };
}

function LeadStub() {
  return <div>Lead detail page</div>;
}

function renderDetail(name = NAME) {
  return renderWithProviders(
    <Routes>
      <Route path="/companies/:name" element={<CompanyDetailsPage />} />
      <Route path="/companies" element={<div>Companies list</div>} />
      <Route path="/leads/:id" element={<LeadStub />} />
    </Routes>,
    { route: `/companies/${encodeURIComponent(name)}` },
  );
}

beforeEach(() => getLeadsMock.mockReset());
afterEach(() => vi.clearAllMocks());

describe('CompanyDetailsPage', () => {
  it('renders the company profile and KPIs', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();

    await screen.findByText(/signals & opportunities/i);
    expect(screen.getByRole('heading', { name: NAME })).toBeInTheDocument();
    expect(screen.getByText('BFSI • Pune')).toBeInTheDocument();

    // Best score aggregates to the strongest lead (92), not the coincidental 99.
    const bestScoreCard = screen.getByText('Best score').closest('.card') as HTMLElement;
    expect(within(bestScoreCard).getByText(/92/)).toBeInTheDocument();
    // Estimated hiring sums across the company's leads (40 + 15).
    const hiringCard = screen.getByText('Est. hiring').closest('.card') as HTMLElement;
    expect(within(hiringCard).getByText('55')).toBeInTheDocument();
  });

  it('unions the technology stack across leads', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await screen.findByText(/signals & opportunities/i);

    expect(screen.getByText('AWS')).toBeInTheDocument();
    // "React" only appears on the second lead — proves the union.
    expect(screen.getByText('React')).toBeInTheDocument();
  });

  it('lists only this company’s signals and drops coincidental hits', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await screen.findByText(/signals & opportunities/i);

    expect(screen.getByText(/signals & opportunities \(2\)/i)).toBeInTheDocument();
    const table = screen.getByRole('table');
    // Header + 2 data rows (the "Other Corp" lead is excluded).
    expect(within(table).getAllByRole('row')).toHaveLength(3);
    expect(within(table).getByText('Core banking modernization')).toBeInTheDocument();
    expect(screen.queryByText('Other Corp')).not.toBeInTheDocument();
  });

  it('renders key contacts from the leads', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await screen.findByText(/signals & opportunities/i);

    expect(screen.getByText('Priya Raman')).toBeInTheDocument();
    expect(screen.getByText('VP of Engineering')).toBeInTheDocument();
  });

  it('navigates to a lead’s details from a signal row', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await screen.findByText(/signals & opportunities/i);

    await userEvent.click(screen.getByRole('button', { name: /view lead 1/i }));
    expect(await screen.findByText('Lead detail page')).toBeInTheDocument();
  });

  it('shows a loading skeleton', async () => {
    let resolve!: (value: LeadListResponse) => void;
    getLeadsMock.mockReturnValue(new Promise<LeadListResponse>((r) => (resolve = r)));
    renderDetail();
    expect(screen.getByTestId('company-skeleton')).toBeInTheDocument();
    resolve(response(LEADS));
    await screen.findByText(/signals & opportunities/i);
  });

  it('shows an error state with retry', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    getLeadsMock.mockRejectedValueOnce(new Error('boom'));
    renderDetail();
    expect(await screen.findByText(/unable to load this company/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('shows a not-found state when no lead matches the name', async () => {
    getLeadsMock.mockResolvedValue(response([makeLead({ id: 9, company_name: 'Someone Else' })]));
    renderDetail('Ghost Company');
    expect(await screen.findByText(/company not found/i)).toBeInTheDocument();
  });

  it('links back to the companies list', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await screen.findByText(/signals & opportunities/i);

    const back = screen.getByRole('link', { name: /back to companies/i });
    await userEvent.click(back);
    expect(await screen.findByText('Companies list')).toBeInTheDocument();
  });
});
