import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { OpportunitiesPage } from './OpportunitiesPage';
import type { Lead, LeadListResponse } from '@/types/lead';

vi.mock('@/services/leads', () => ({ getLeads: vi.fn() }));
import { getLeads } from '@/services/leads';
const getLeadsMock = vi.mocked(getLeads);

const FIXED_NOW = Date.parse('2026-09-30T00:00:00Z');

function makeLead(p: Partial<Lead> & Pick<Lead, 'id' | 'company_name'>): Lead {
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
    location: 'Pune',
    company_size: null,
    company_website: null,
    signal_type: 'HIRING',
    signal_title: 'Signal',
    signal_description: null,
    signal_date: '2026-09-20T00:00:00Z',
    source_name: 'source',
    source_url: null,
    technologies: ['Java'],
    project_name: null,
    project_value: null,
    estimated_hiring: 5,
    hiring_roles: [],
    poc_name: null,
    poc_title: null,
    poc_linkedin_url: null,
    public_contact: null,
    signal_confidence: 80,
    lead_score: 60,
    lead_priority: 'WARM',
    opportunity_summary: null,
    recommended_action: null,
    recommended_pitch: null,
    status: 'NEW',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    last_verified_at: null,
    ...p,
  };
}

const LEADS: Lead[] = [
  makeLead({
    id: 1,
    company_name: 'NorthStar Banking',
    industry: 'BFSI',
    signal_type: 'PROJECT_AWARD',
    signal_date: '2026-09-25T00:00:00Z', // 5 days -> CRITICAL
    technologies: ['Java', 'AWS'],
    estimated_hiring: 40,
    poc_name: 'Priya Raman',
    poc_title: 'VP Engineering',
    recommended_action: 'Engage leadership.',
    source_name: 'press release',
    opportunity_summary: 'Large-scale ramp-up.',
    lead_score: 92,
    lead_priority: 'HOT',
    status: 'NEW',
  }),
  makeLead({
    id: 2,
    company_name: 'Helios Health',
    industry: 'Healthcare',
    signal_type: 'HIRING',
    signal_date: '2026-09-10T00:00:00Z', // 20 days -> HIGH
    technologies: ['Python'],
    estimated_hiring: 5,
    lead_score: 60,
    lead_priority: 'WARM',
  }),
  makeLead({
    id: 3,
    company_name: 'Vertex Cloud',
    industry: 'IT',
    signal_type: 'VENDOR_REQUIREMENT',
    signal_date: '2026-08-01T00:00:00Z', // 60 days -> MEDIUM
    technologies: ['AWS'],
    estimated_hiring: null,
    lead_score: 70,
    lead_priority: 'NURTURE',
  }),
];

function response(items: Lead[]): LeadListResponse {
  return { items, total: items.length, page: 1, page_size: 100, total_pages: 1 };
}

function LeadStub() {
  return <div>Lead detail page</div>;
}

function renderPage(route = '/opportunities') {
  return renderWithProviders(
    <Routes>
      <Route path="/opportunities" element={<OpportunitiesPage />} />
      <Route path="/leads" element={<div>Leads list page</div>} />
      <Route path="/leads/:id" element={<LeadStub />} />
    </Routes>,
    { route },
  );
}

const table = () => screen.getByRole('table');

let nowSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  getLeadsMock.mockReset();
  nowSpy = vi.spyOn(Date, 'now').mockReturnValue(FIXED_NOW);
});
afterEach(() => {
  nowSpy.mockRestore();
  vi.clearAllMocks();
});

describe('OpportunitiesPage', () => {
  it('renders the page and funnel from derived opportunities', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();

    await screen.findByRole('table');
    expect(screen.getByRole('heading', { name: 'Opportunities' })).toBeInTheDocument();
    expect(screen.getByText(/prioritize qualified business opportunities/i)).toBeInTheDocument();
    // Funnel Total = 3.
    const totalCard = screen.getByText('Total').closest('.card') as HTMLElement;
    expect(within(totalCard).getByText('3')).toBeInTheDocument();
  });

  it('lists opportunities with derived types', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    expect(within(table()).getAllByRole('row')).toHaveLength(4); // header + 3
    expect(within(table()).getByText('NorthStar Banking')).toBeInTheDocument();
    expect(within(table()).getByText('Vendor Opportunity')).toBeInTheDocument(); // Vertex
    expect(within(table()).getByText('Large-Scale Ramp-Up')).toBeInTheDocument(); // NorthStar (40 hires)
  });

  it('also renders mobile cards (responsive dual-render)', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');
    // Company appears in both the table and a card.
    expect(screen.getAllByText('NorthStar Banking').length).toBeGreaterThan(1);
  });

  it('debounces search and filters the table', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.type(screen.getByLabelText('Search'), 'helios');
    await waitFor(() =>
      expect(within(table()).queryByText('NorthStar Banking')).not.toBeInTheDocument(),
    );
    expect(within(table()).getByText('Helios Health')).toBeInTheDocument();
  });

  it('filters by opportunity type', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.selectOptions(screen.getByLabelText('Opportunity type'), 'VENDOR_OPPORTUNITY');
    await waitFor(() => expect(within(table()).getAllByRole('row')).toHaveLength(2));
    expect(within(table()).getByText('Vertex Cloud')).toBeInTheDocument();
  });

  it('filters by priority', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.selectOptions(screen.getByLabelText('Priority'), 'HOT');
    await waitFor(() => expect(within(table()).getAllByRole('row')).toHaveLength(2));
    expect(within(table()).getByText('NorthStar Banking')).toBeInTheDocument();
  });

  it('filters by staffing need', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.selectOptions(screen.getByLabelText('Staffing need'), 'HIGH');
    await waitFor(() => expect(within(table()).getAllByRole('row')).toHaveLength(2));
    expect(within(table()).getByText('NorthStar Banking')).toBeInTheDocument();
  });

  it('filters by urgency (recency-derived)', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.selectOptions(screen.getByLabelText('Urgency'), 'HIGH');
    await waitFor(() => expect(within(table()).getAllByRole('row')).toHaveLength(2));
    expect(within(table()).getByText('Helios Health')).toBeInTheDocument(); // 20 days -> HIGH
  });

  it('filters by industry and technology', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.type(screen.getByLabelText('Technology'), 'python');
    await waitFor(() => expect(within(table()).getAllByRole('row')).toHaveLength(2));
    expect(within(table()).getByText('Helios Health')).toBeInTheDocument();
  });

  it('filters by status', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.selectOptions(screen.getByLabelText('Status'), 'NEW');
    // NorthStar + Helios + Vertex all default NEW -> all 3 remain.
    await waitFor(() => expect(within(table()).getAllByRole('row')).toHaveLength(4));
  });

  it('sorts by estimated team', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.selectOptions(screen.getByLabelText('Sort by'), 'team');
    await waitFor(() => {
      const rows = within(table()).getAllByRole('row');
      // NorthStar(40), Helios(5), Vertex(null)
      expect(within(rows[1]).getByText('NorthStar Banking')).toBeInTheDocument();
      expect(within(rows[2]).getByText('Helios Health')).toBeInTheDocument();
    });
  });

  it('shows top opportunities by score', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    const top = screen.getByText('Top opportunities').closest('.card') as HTMLElement;
    expect(within(top).getByText('NorthStar Banking')).toBeInTheDocument();
    expect(within(top).getByText('92')).toBeInTheDocument();
  });

  it('opens a detail drawer with evidence, POC, action and no fabricated confidence', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.click(
      within(table()).getByRole('button', { name: /view opportunity for northstar banking/i }),
    );
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Large-scale ramp-up.')).toBeInTheDocument(); // business reason
    expect(within(dialog).getByText(/VP Engineering/)).toBeInTheDocument(); // POC
    expect(within(dialog).getByText('Engage leadership.')).toBeInTheDocument(); // recommended action
    expect(within(dialog).getByText('press release')).toBeInTheDocument(); // evidence source
    expect(within(dialog).getAllByText('Not available').length).toBeGreaterThan(0); // opportunity confidence
  });

  it('navigates to the full lead from the drawer', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.click(
      within(table()).getByRole('button', { name: /view opportunity for northstar banking/i }),
    );
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('link', { name: /view full lead/i }));
    expect(await screen.findByText('Lead detail page')).toBeInTheDocument();
  });

  it('applies a quick-filter tab and clears filters', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.click(screen.getByRole('tab', { name: /🔥 hot/i }));
    await waitFor(() => expect(within(table()).getAllByRole('row')).toHaveLength(2));
    expect(screen.getByText('Priority: HOT')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /clear all/i }));
    await waitFor(() => expect(within(table()).getAllByRole('row')).toHaveLength(4));
  });

  it('shows a loading skeleton', async () => {
    let resolve!: (value: LeadListResponse) => void;
    getLeadsMock.mockReturnValue(new Promise<LeadListResponse>((r) => (resolve = r)));
    renderPage();
    expect(screen.getByTestId('opportunities-skeleton')).toBeInTheDocument();
    resolve(response(LEADS));
    await screen.findByRole('table');
  });

  it('shows an error state', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    getLeadsMock.mockRejectedValueOnce(new Error('boom'));
    renderPage();
    expect(await screen.findByText(/unable to load opportunities/i)).toBeInTheDocument();
  });

  it('shows an empty state', async () => {
    getLeadsMock.mockResolvedValue(response([]));
    renderPage();
    expect(await screen.findByText(/no opportunities found/i)).toBeInTheDocument();
  });
});
