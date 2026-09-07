import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { ContactsPage } from './ContactsPage';
import type { Lead, LeadListResponse } from '@/types/lead';

vi.mock('@/services/leads', () => ({ getLeads: vi.fn() }));
import { getLeads } from '@/services/leads';
const getLeadsMock = vi.mocked(getLeads);

// Mock only the network fns; keep the real display helpers (verificationDisplay…).
vi.mock('@/services/decisionMakers', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/decisionMakers')>();
  return { ...actual, fetchContacts: vi.fn(), fetchLeadStakeholders: vi.fn() };
});
import { fetchContacts, type DecisionMakerList } from '@/services/decisionMakers';
const fetchContactsMock = vi.mocked(fetchContacts);

const emptyContacts: DecisionMakerList = { items: [], total: 0, page: 1, page_size: 20, total_pages: 0 };

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
    signal_date: '2026-09-25T00:00:00Z',
    source_name: 'source',
    source_url: null,
    technologies: [],
    project_name: null,
    project_value: null,
    estimated_hiring: 10,
    hiring_roles: [],
    poc_name: null,
    poc_title: 'VP of Engineering',
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
    poc_title: 'VP of Engineering',
    signal_type: 'PROJECT_AWARD',
    estimated_hiring: 40,
    source_name: 'press release',
    recommended_action: 'Engage leadership.',
    opportunity_summary: 'Large-scale ramp-up.',
    lead_score: 88,
    lead_priority: 'HOT',
  }),
  makeLead({
    id: 2,
    company_name: 'Helios Health',
    industry: 'Healthcare',
    poc_title: 'Procurement Head',
    signal_type: 'VENDOR_REQUIREMENT',
    lead_score: 65,
    lead_priority: 'WARM',
  }),
  makeLead({ id: 3, company_name: 'Vertex Cloud', industry: 'IT', poc_title: 'CTO', lead_score: 40, lead_priority: 'LOW' }),
  makeLead({ id: 4, company_name: 'NEC', poc_title: null }), // no role -> no recommendation
];

function response(items: Lead[]): LeadListResponse {
  return { items, total: items.length, page: 1, page_size: 100, total_pages: 1 };
}

function renderPage(route = '/contacts') {
  return renderWithProviders(
    <Routes>
      <Route path="/contacts" element={<ContactsPage />} />
      <Route path="/leads" element={<div>Leads list page</div>} />
      <Route path="/leads/:id" element={<div>Lead detail page</div>} />
      <Route path="/companies/:name" element={<div>Company detail page</div>} />
    </Routes>,
    { route },
  );
}

const table = () => screen.getByRole('table');

let nowSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  getLeadsMock.mockReset();
  fetchContactsMock.mockReset();
  fetchContactsMock.mockResolvedValue(emptyContacts);
  nowSpy = vi.spyOn(Date, 'now').mockReturnValue(FIXED_NOW);
});
afterEach(() => {
  nowSpy.mockRestore();
  vi.clearAllMocks();
});

describe('ContactsPage', () => {
  it('renders role recommendations and summary (excludes leads with no role)', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    const total = screen.getByText('Role recommendations').closest('.card') as HTMLElement;
    expect(within(total).getByText('3')).toBeInTheDocument(); // NEC excluded
    expect(within(table()).getByText('VP of Engineering')).toBeInTheDocument();
  });

  it('shows decision-maker type, relevance and confidence', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    const row = within(table()).getByText('NorthStar Banking').closest('tr') as HTMLElement;
    expect(within(row).getByText('Technical')).toBeInTheDocument();
    expect(within(row).getByText('88')).toBeInTheDocument(); // relevance (= lead score)
    expect(within(row).getAllByText('HIGH').length).toBeGreaterThan(0);
    expect(within(within(table()).getByText('Helios Health').closest('tr') as HTMLElement).getByText('Procurement')).toBeInTheDocument();
  });

  it('shows "Person not identified yet" instead of a fabricated name', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');
    expect(within(table()).getAllByText(/person not identified yet/i).length).toBeGreaterThan(0);
  });

  it('searches by company', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.type(screen.getByLabelText('Search'), 'helios');
    await waitFor(() => expect(within(table()).queryByText('NorthStar Banking')).not.toBeInTheDocument());
    expect(within(table()).getByText('Helios Health')).toBeInTheDocument();
  });

  it('filters by decision-maker type', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.selectOptions(screen.getByLabelText('Decision-maker type'), 'PROCUREMENT');
    await waitFor(() => expect(within(table()).getAllByRole('row')).toHaveLength(2));
    expect(within(table()).getByText('Helios Health')).toBeInTheDocument();
  });

  it('filters by priority and shows a removable chip, then clears', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.selectOptions(screen.getByLabelText('Priority'), 'HOT');
    await waitFor(() => expect(within(table()).getAllByRole('row')).toHaveLength(2));
    expect(screen.getByText('Priority: HOT')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /clear all/i }));
    await waitFor(() => expect(within(table()).getAllByRole('row')).toHaveLength(4));
  });

  it('sorts by company', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.selectOptions(screen.getByLabelText('Sort by'), 'company');
    await waitFor(() => {
      const rows = within(table()).getAllByRole('row');
      expect(within(rows[1]).getByText('Helios Health')).toBeInTheDocument(); // alphabetical
    });
  });

  it('groups by company with a primary role', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.click(screen.getByRole('tab', { name: /by company/i }));
    await waitFor(() => expect(screen.queryByRole('table')).not.toBeInTheDocument());
    const group = screen.getByText('NorthStar Banking').closest('.card') as HTMLElement;
    expect(within(group).getByText('Primary')).toBeInTheDocument();
    expect(within(group).getByText('VP of Engineering')).toBeInTheDocument();
  });

  it('shows top target roles', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    const top = screen.getByText('Top target roles').closest('.card') as HTMLElement;
    expect(within(top).getByText('VP of Engineering')).toBeInTheDocument();
  });

  it('opens a detail drawer with context, no fabricated reason, and evidence', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.click(
      within(table()).getByRole('button', { name: /view vp of engineering recommendation for northstar/i }),
    );
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Large-Scale Ramp-Up')).toBeInTheDocument(); // opportunity context
    expect(within(dialog).getByText('Engage leadership.')).toBeInTheDocument(); // recommended action
    expect(within(dialog).getByText('press release')).toBeInTheDocument(); // evidence
    expect(within(dialog).getAllByText('Not available').length).toBeGreaterThan(0); // POC reason not persisted
    expect(within(dialog).getByText(/person not identified yet/i)).toBeInTheDocument();
  });

  it('navigates to the lead and company from the drawer', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('table');

    await userEvent.click(
      within(table()).getByRole('button', { name: /view vp of engineering recommendation for northstar/i }),
    );
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('link', { name: /view lead/i })).toHaveAttribute('href', '/leads/1');
    await userEvent.click(within(dialog).getByRole('link', { name: /view company/i }));
    expect(await screen.findByText('Company detail page')).toBeInTheDocument();
  });

  it('shows a loading skeleton', async () => {
    let resolve!: (value: LeadListResponse) => void;
    getLeadsMock.mockReturnValue(new Promise<LeadListResponse>((r) => (resolve = r)));
    renderPage();
    expect(screen.getByTestId('contacts-skeleton')).toBeInTheDocument();
    resolve(response(LEADS));
    await screen.findByRole('table');
  });

  it('shows an error state', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    getLeadsMock.mockRejectedValueOnce(new Error('boom'));
    renderPage();
    expect(await screen.findByText(/unable to load decision-maker recommendations/i)).toBeInTheDocument();
  });

  it('shows an empty state when no lead has a recommended role', async () => {
    getLeadsMock.mockResolvedValue(response([makeLead({ id: 9, company_name: 'NoRole', poc_title: null })]));
    renderPage();
    expect(await screen.findByText(/no decision-maker recommendations yet/i)).toBeInTheDocument();
  });

  it('shows the verified people & contacts section with an honest empty state', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    const section = await screen.findByTestId('verified-contacts-section');
    expect(within(section).getByText(/verified people & contacts/i)).toBeInTheDocument();
    expect(await within(section).findByText(/no verified people or contacts yet/i)).toBeInTheDocument();
    // The derived section is clearly relabelled as NOT verified people.
    expect(screen.getByText(/recommended roles \(not verified people\)/i)).toBeInTheDocument();
  });

  it('renders real verified people/contacts from the backend', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    fetchContactsMock.mockResolvedValue({
      ...emptyContacts,
      total: 1,
      items: [
        {
          id: 'dm-1',
          company_id: 1,
          company_name: 'NorthStar Banking',
          full_name: 'Asha Verma',
          job_title: 'VP Engineering',
          normalized_role: 'vp_engineering',
          role_category: 'TECHNICAL',
          department: 'Engineering',
          seniority: 'VP',
          profile_url: null,
          professional_network_url: null,
          business_email: 'asha@northstar.example',
          business_phone: null,
          contact_type: 'PERSON',
          email_status: 'VALID',
          contact_source: 'Company site',
          source_type: 'WEBSITE',
          source_url: 'https://northstar.example/team',
          identity_confidence: 90,
          role_confidence: 85,
          company_confidence: 88,
          contact_confidence: 80,
          evidence_confidence: 82,
          freshness_score: 75,
          verification_status: 'VERIFIED',
          match_status: null,
          data_provenance: 'REAL',
          last_verified_at: '2026-09-01T00:00:00Z',
        },
      ],
    });
    renderPage();
    const section = await screen.findByTestId('verified-contacts-section');
    expect(await within(section).findByText('Asha Verma')).toBeInTheDocument();
    expect(within(section).getByText('Verified')).toBeInTheDocument();
    expect(within(section).getByRole('link', { name: /company site/i })).toHaveAttribute(
      'href',
      'https://northstar.example/team',
    );
  });
});
