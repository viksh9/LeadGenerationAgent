import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { OutreachPage } from './OutreachPage';
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
    industry: 'BFSI',
    location: 'Pune',
    company_size: null,
    company_website: null,
    signal_type: 'PROJECT_AWARD',
    signal_title: 'x',
    signal_description: null,
    signal_date: '2026-09-25T00:00:00Z',
    source_name: 'press release',
    source_url: null,
    technologies: ['Java'],
    project_name: null,
    project_value: null,
    estimated_hiring: 40,
    hiring_roles: [],
    poc_name: null,
    poc_title: 'VP of Engineering',
    poc_linkedin_url: null,
    public_contact: null,
    signal_confidence: 90,
    lead_score: 88,
    lead_priority: 'HOT',
    opportunity_summary: 'Large ramp-up.',
    recommended_action: 'Engage leadership.',
    recommended_pitch: 'Subject: Scaling your team\n\nWe noticed you are expanding.',
    status: 'NEW',
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    last_verified_at: null,
    ...p,
  };
}

const LEADS: Lead[] = [
  makeLead({ id: 1, company_name: 'NorthStar Banking', lead_priority: 'HOT', lead_score: 88 }),
  makeLead({ id: 2, company_name: 'Helios Health', industry: 'Healthcare', signal_type: 'HIRING', estimated_hiring: 5, lead_priority: 'WARM', lead_score: 65, poc_title: 'CIO' }),
  makeLead({ id: 3, company_name: 'Weak Co', lead_priority: 'LOW', lead_score: 20, recommended_pitch: null, poc_title: null }),
];

function response(items: Lead[]): LeadListResponse {
  return { items, total: items.length, page: 1, page_size: 100, total_pages: 1 };
}

function renderPage(route = '/outreach') {
  return renderWithProviders(
    <Routes>
      <Route path="/outreach" element={<OutreachPage />} />
      <Route path="/leads" element={<div>Leads list page</div>} />
      <Route path="/leads/:id" element={<div>Lead detail page</div>} />
      <Route path="/companies/:name" element={<div>Company detail page</div>} />
    </Routes>,
    { route },
  );
}

function section(name: RegExp): HTMLElement {
  return screen.getByRole('heading', { name }).closest('div') as HTMLElement;
}
const readyTable = () => within(section(/ready for outreach/i)).getByRole('table');

let nowSpy: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  getLeadsMock.mockReset();
  nowSpy = vi.spyOn(Date, 'now').mockReturnValue(FIXED_NOW);
});
afterEach(() => {
  nowSpy.mockRestore();
  vi.clearAllMocks();
});

describe('OutreachPage', () => {
  it('renders the queue split with a summary', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('heading', { name: /ready for outreach/i });

    const ready = screen.getByText('Ready for outreach').closest('.card') as HTMLElement;
    expect(within(ready).getByText('2')).toBeInTheDocument();
    // HOT and WARM are outreach-ready; the LOW no-pitch lead needs review.
    expect(within(readyTable()).getByText('NorthStar Banking')).toBeInTheDocument();
    expect(within(readyTable()).getByText('Helios Health')).toBeInTheDocument();
    const review = within(section(/needs review/i)).getByRole('table');
    expect(within(review).getByText('Weak Co')).toBeInTheDocument();
  });

  it('prioritizes HOT before WARM in the ready queue', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('heading', { name: /ready for outreach/i });

    const rows = within(readyTable()).getAllByRole('row');
    expect(within(rows[1]).getByText('NorthStar Banking')).toBeInTheDocument(); // HOT first
    expect(within(rows[2]).getByText('Helios Health')).toBeInTheDocument();
  });

  it('searches the queue', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('heading', { name: /ready for outreach/i });

    await userEvent.type(screen.getByLabelText('Search'), 'helios');
    await waitFor(() => expect(within(readyTable()).queryByText('NorthStar Banking')).not.toBeInTheDocument());
    expect(within(readyTable()).getByText('Helios Health')).toBeInTheDocument();
  });

  it('filters by opportunity type', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('heading', { name: /ready for outreach/i });

    // NorthStar (PROJECT_AWARD + 40) -> Large-Scale Ramp-Up.
    await userEvent.selectOptions(screen.getByLabelText('Opportunity type'), 'LARGE_SCALE_RAMP_UP');
    await waitFor(() => expect(within(readyTable()).queryByText('Helios Health')).not.toBeInTheDocument());
    expect(within(readyTable()).getByText('NorthStar Banking')).toBeInTheDocument();
  });

  it('opens the detail drawer with channel tabs and derived context', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('heading', { name: /ready for outreach/i });

    await userEvent.click(
      within(readyTable()).getByRole('button', { name: /review outreach for northstar/i }),
    );
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Project Ramp-Up')).toBeInTheDocument(); // message strategy
    expect(within(dialog).getByText('Not available')).toBeInTheDocument(); // pitch confidence
    expect(within(dialog).getByText('We noticed you are expanding.')).toBeInTheDocument(); // email body
  });

  it('shows honest empty channel messages for LinkedIn and Call', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('heading', { name: /ready for outreach/i });

    await userEvent.click(
      within(readyTable()).getByRole('button', { name: /review outreach for northstar/i }),
    );
    const dialog = await screen.findByRole('dialog');

    await userEvent.click(within(dialog).getByRole('tab', { name: 'LinkedIn' }));
    expect(within(dialog).getByText(/no linkedin message has been generated/i)).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole('tab', { name: 'Call' }));
    expect(within(dialog).getByText(/no call talking points have been generated/i)).toBeInTheDocument();
  });

  it('copies the email message', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    renderPage();
    await screen.findByRole('heading', { name: /ready for outreach/i });

    await userEvent.click(
      within(readyTable()).getByRole('button', { name: /review outreach for northstar/i }),
    );
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: /copy email/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining('We noticed')));
  });

  it('edits a message and can reset with confirmation', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('heading', { name: /ready for outreach/i });

    await userEvent.click(
      within(readyTable()).getByRole('button', { name: /review outreach for northstar/i }),
    );
    const dialog = await screen.findByRole('dialog');
    const body = within(dialog).getByLabelText('Message');
    await userEvent.type(body, ' Extra text.');
    expect(within(dialog).getByText(/unsaved changes/i)).toBeInTheDocument();

    // The enabled Reset button belongs to the edited Message editor.
    const reset = within(dialog)
      .getAllByRole('button', { name: /reset to generated message/i })
      .find((b) => !b.hasAttribute('disabled')) as HTMLElement;
    await userEvent.click(reset);
    // Confirmation dialog, then confirm.
    await userEvent.click(screen.getByRole('button', { name: 'Reset' }));
    await waitFor(() => expect(within(dialog).queryByText(/unsaved changes/i)).not.toBeInTheDocument());
  });

  it('navigates to the lead and company from the drawer', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('heading', { name: /ready for outreach/i });

    await userEvent.click(
      within(readyTable()).getByRole('button', { name: /review outreach for northstar/i }),
    );
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('link', { name: /^view lead$/i })).toHaveAttribute('href', '/leads/1');
    await userEvent.click(within(dialog).getByRole('link', { name: /^view company$/i }));
    expect(await screen.findByText('Company detail page')).toBeInTheDocument();
  });

  it('shows the follow-up placeholder', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    renderPage();
    await screen.findByRole('heading', { name: /ready for outreach/i });
    expect(screen.getByText(/follow-up tracking will be available/i)).toBeInTheDocument();
  });

  it('shows a loading skeleton', async () => {
    let resolve!: (value: LeadListResponse) => void;
    getLeadsMock.mockReturnValue(new Promise<LeadListResponse>((r) => (resolve = r)));
    renderPage();
    expect(screen.getByTestId('outreach-skeleton')).toBeInTheDocument();
    resolve(response(LEADS));
    await screen.findByRole('heading', { name: /ready for outreach/i });
  });

  it('shows an error state', async () => {
    getLeadsMock.mockResolvedValue(response(LEADS));
    getLeadsMock.mockRejectedValueOnce(new Error('boom'));
    renderPage();
    expect(await screen.findByText(/unable to load outreach opportunities/i)).toBeInTheDocument();
  });

  it('shows an empty state when there are no leads', async () => {
    getLeadsMock.mockResolvedValue(response([]));
    renderPage();
    expect(await screen.findByText(/no outreach opportunities are ready yet/i)).toBeInTheDocument();
  });
});
