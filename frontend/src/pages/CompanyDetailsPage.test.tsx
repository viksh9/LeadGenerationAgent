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
    signal_title: 'Hiring engineers',
    signal_description: 'Scaling the platform team.',
    signal_date: '2026-09-01T00:00:00Z',
    source_name: 'press release',
    source_url: 'https://news.example/northstar',
    technologies: ['Java', 'AWS'],
    project_name: null,
    project_value: null,
    estimated_hiring: 15,
    hiring_roles: ['Java Engineer'],
    poc_name: null,
    poc_title: null,
    poc_linkedin_url: null,
    public_contact: null,
    signal_confidence: 55,
    lead_score: 60,
    lead_priority: 'WARM',
    opportunity_summary: 'Team expansion opportunity.',
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
    signal_description: 'Won a modernization project.',
    signal_date: '2026-09-04T00:00:00Z',
    signal_confidence: 90,
    technologies: ['Java', 'AWS'],
    estimated_hiring: 40,
    hiring_roles: ['Java Engineer', 'AWS Engineer'],
    project_name: 'Core Banking Revamp',
    project_value: 2500000,
    poc_name: 'Priya Raman',
    poc_title: 'VP of Engineering',
    poc_linkedin_url: 'https://linkedin.com/in/priya',
    lead_score: 92,
    lead_priority: 'HOT',
    opportunity_summary: 'Large-scale ramp-up.',
    recommended_action: 'Engage the VP Engineering team within 48 hours.',
  }),
  makeLead({
    id: 2,
    company_name: NAME,
    signal_type: 'HIRING',
    technologies: ['Java', 'React'],
    poc_title: 'CTO',
    lead_score: 60,
    lead_priority: 'WARM',
  }),
  // Coincidental fuzzy-search hit — filtered out by exact name match.
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
      <Route path="/leads" element={<div>Leads list</div>} />
      <Route path="/leads/:id" element={<LeadStub />} />
    </Routes>,
    { route: `/companies/${encodeURIComponent(name)}` },
  );
}

/** Success-only anchor: this heading appears only once data has aggregated. */
const ready = () => screen.findByText('Account opportunity summary');

beforeEach(() => getLeadsMock.mockReset());
afterEach(() => vi.clearAllMocks());

describe('CompanyDetailsPage', () => {
  it('renders account identity and overview', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await ready();

    expect(screen.getByRole('heading', { name: NAME })).toBeInTheDocument();
    expect(screen.getByText('BFSI • Pune')).toBeInTheDocument();
    const overview = screen.getByText('Company overview').closest('.card') as HTMLElement;
    expect(within(overview).getByText('BFSI')).toBeInTheDocument();
  });

  it('summarizes account metrics from the strongest leads', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await ready();

    const summary = screen.getByText('Account opportunity summary').closest('.card') as HTMLElement;
    // 2 opportunities, summed hiring 55, HIGH staffing band, highest score 92.
    expect(within(summary).getByText(/92 \/ 100/)).toBeInTheDocument();
    expect(within(summary).getByText('55')).toBeInTheDocument();
    expect(within(summary).getByText('HIGH')).toBeInTheDocument();
  });

  it('shows the technology landscape sorted with frequencies', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await ready();

    const tl = screen.getByText('Technology landscape').closest('.card') as HTMLElement;
    expect(within(tl).getByText('Java')).toBeInTheDocument(); // in both leads
    expect(within(tl).getByText('AWS')).toBeInTheDocument();
    expect(within(tl).getByText('React')).toBeInTheDocument();
    // Java appears in 2 leads.
    expect(within(tl).getByLabelText('2 related leads')).toBeInTheDocument();
  });

  it('renders a signal timeline newest first and humanizes types', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await ready();

    const timeline = screen.getByText('Signal timeline').closest('.card') as HTMLElement;
    const items = within(timeline).getAllByRole('listitem');
    // Newest (Project Award, Sep 04) before older (Hiring, Sep 01).
    expect(within(items[0]).getByText('Project Award')).toBeInTheDocument();
    expect(within(timeline).getByText('Core banking modernization')).toBeInTheDocument();
    expect(within(timeline).queryByText('PROJECT_AWARD')).not.toBeInTheDocument();
  });

  it('shows hiring intelligence with an available-data estimate', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await ready();

    const hiring = screen.getByText('Hiring intelligence').closest('.card') as HTMLElement;
    expect(within(hiring).getByText('55')).toBeInTheDocument();
    expect(within(hiring).getByText('Java Engineer')).toBeInTheDocument();
    expect(within(hiring).getByText(/based on available lead data/i)).toBeInTheDocument();
  });

  it('shows project intelligence only when a project exists', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await ready();

    const projects = screen.getByText('Project intelligence').closest('.card') as HTMLElement;
    expect(within(projects).getByText('Core Banking Revamp')).toBeInTheDocument();
  });

  it('aggregates decision-maker roles without duplicates', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await ready();

    const dm = screen.getByText('Recommended decision-makers').closest('.card') as HTMLElement;
    expect(within(dm).getByText('VP of Engineering')).toBeInTheDocument();
    expect(within(dm).getByText('CTO')).toBeInTheDocument();
    expect(within(dm).getByText('Priya Raman')).toBeInTheDocument();
  });

  it('lists related leads and drops coincidental company hits', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await ready();

    expect(screen.getByText('Related leads (2)')).toBeInTheDocument();
    expect(screen.queryByText('Other Corp')).not.toBeInTheDocument();
  });

  it('renders the sources & evidence section', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await ready();

    const evidence = screen.getByText('Sources & evidence').closest('.card') as HTMLElement;
    expect(within(evidence).getAllByText('press release').length).toBeGreaterThan(0);
  });

  it('shows a recommended account action from the strongest lead', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await ready();

    expect(screen.getByText('Recommended action')).toBeInTheDocument();
    expect(screen.getByText(/engage the vp engineering team within 48 hours/i)).toBeInTheDocument();
  });

  it('navigates to a lead from the signal timeline', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await ready();

    await userEvent.click(screen.getByRole('button', { name: /view lead 1 for signal/i }));
    expect(await screen.findByText('Lead detail page')).toBeInTheDocument();
  });

  it('links out to the filtered leads list', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await ready();

    const viewLeads = screen.getByRole('link', { name: /^view leads$/i });
    expect(viewLeads).toHaveAttribute('href', expect.stringContaining('/leads?search='));
  });

  it('handles missing optional data without null/undefined', async () => {
    getLeadsMock.mockResolvedValue(
      response([
        makeLead({
          id: 5,
          company_name: NAME,
          technologies: [],
          hiring_roles: [],
          estimated_hiring: null,
          project_name: null,
          poc_name: null,
          poc_title: null,
          source_name: null,
          source_url: null,
        }),
      ]),
    );
    renderDetail();
    await ready();

    expect(screen.getByText(/no technologies detected/i)).toBeInTheDocument();
    expect(screen.getByText(/no projects referenced/i)).toBeInTheDocument();
    expect(screen.queryByText(/undefined|null|NaN/)).not.toBeInTheDocument();
  });

  it('shows a loading skeleton', async () => {
    let resolve!: (value: LeadListResponse) => void;
    getLeadsMock.mockReturnValue(new Promise<LeadListResponse>((r) => (resolve = r)));
    renderDetail();
    expect(screen.getByTestId('company-skeleton')).toBeInTheDocument();
    resolve(response(LEADS));
    await ready();
  });

  it('shows an error state', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    getLeadsMock.mockRejectedValueOnce(new Error('boom'));
    renderDetail();
    expect(await screen.findByText(/unable to load company intelligence/i)).toBeInTheDocument();
  });

  it('shows a not-found state when no lead matches', async () => {
    getLeadsMock.mockResolvedValue(response([makeLead({ id: 9, company_name: 'Someone Else' })]));
    renderDetail('Ghost Company');
    expect(await screen.findByText(/company not found/i)).toBeInTheDocument();
  });

  it('links back to the companies list', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderDetail();
    await ready();

    await userEvent.click(screen.getByRole('link', { name: /back to companies/i }));
    expect(await screen.findByText('Companies list')).toBeInTheDocument();
  });
});
