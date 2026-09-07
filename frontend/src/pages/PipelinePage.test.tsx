import { screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { PipelinePage } from './PipelinePage';
import type { CRMAnalytics, PipelineBoard, SalesOpportunity } from '@/services/crm';

// Keep the real display helpers + formatters; stub only the network fetchers.
vi.mock('@/services/crm', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/crm')>();
  return { ...actual, fetchPipelineBoard: vi.fn(), fetchCrmAnalytics: vi.fn() };
});
import { fetchCrmAnalytics, fetchPipelineBoard } from '@/services/crm';
const fetchBoardMock = vi.mocked(fetchPipelineBoard);
const fetchAnalyticsMock = vi.mocked(fetchCrmAnalytics);

function makeOpp(p: Partial<SalesOpportunity> = {}): SalesOpportunity {
  return {
    id: 1,
    company_id: 10,
    lead_id: 7,
    opportunity_candidate_id: null,
    opportunity_type: 'STAFFING',
    title: 'NorthStar core banking ramp-up',
    description: null,
    estimated_team_scale: null,
    estimated_value: null,
    estimated_value_currency: null,
    value_source: 'NOT_AVAILABLE',
    confidence: 62,
    evidence_ids: [1, 2],
    stage: 'IDENTIFIED',
    probability: null,
    expected_close_date: null,
    owner: null,
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-02T00:00:00Z',
    ...p,
  };
}

function makeBoard(): PipelineBoard {
  return {
    columns: [
      { stage: 'IDENTIFIED', count: 1, opportunities: [makeOpp()] },
      { stage: 'QUALIFIED', count: 0, opportunities: [] },
    ],
    total: 1,
  };
}

function makeAnalytics(p: Partial<CRMAnalytics> = {}): CRMAnalytics {
  return {
    generated_at: '2026-09-05T10:00:00Z',
    total_leads: 24,
    lead_status_counts: {},
    sales_stage_counts: {},
    activity_counts: {},
    real_contacted: 3,
    real_replies: 1,
    real_meetings: 0,
    conversion: [
      { label: 'Contacted → Replied', numerator: 1, denominator: 3, rate: 0.33 },
      { label: 'Replied → Meeting', numerator: 0, denominator: 1, rate: 'INSUFFICIENT_DATA' },
    ],
    pipeline_value: 'NOT_AVAILABLE',
    pipeline_value_currency: null,
    pipeline_value_opportunities: 0,
    open_opportunities: 1,
    won: 0,
    lost: 0,
    ...p,
  };
}

beforeEach(() => {
  fetchBoardMock.mockReset();
  fetchAnalyticsMock.mockReset();
});
afterEach(() => vi.clearAllMocks());

describe('PipelinePage', () => {
  it('renders board columns, an opportunity card and honest KPIs', async () => {
    fetchBoardMock.mockResolvedValue(makeBoard());
    fetchAnalyticsMock.mockResolvedValue(makeAnalytics());

    renderWithProviders(<PipelinePage />, { route: '/pipeline' });

    // Board columns render by stage label (the stage may also appear on a card
    // badge, so assert at least one match rather than a unique one).
    expect((await screen.findAllByText('Identified', { selector: 'span.badge' })).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Qualified', { selector: 'span.badge' }).length).toBeGreaterThan(0);

    // A real opportunity card shows.
    expect(screen.getByText('NorthStar core banking ramp-up')).toBeInTheDocument();

    // KPI strip.
    expect(screen.getByText('Total leads')).toBeInTheDocument();
    expect(screen.getByText('24')).toBeInTheDocument();
  });

  it('renders pipeline value as "Not available" when NOT_AVAILABLE', async () => {
    fetchBoardMock.mockResolvedValue(makeBoard());
    fetchAnalyticsMock.mockResolvedValue(makeAnalytics());

    renderWithProviders(<PipelinePage />, { route: '/pipeline' });

    await screen.findByText('Pipeline value');
    // Both the KPI and the card value are unavailable — never a fabricated 0.
    expect(screen.getAllByText('Not available').length).toBeGreaterThan(0);
  });

  it('renders a conversion metric as "Insufficient data" for the sentinel rate', async () => {
    fetchBoardMock.mockResolvedValue(makeBoard());
    fetchAnalyticsMock.mockResolvedValue(makeAnalytics());

    renderWithProviders(<PipelinePage />, { route: '/pipeline' });

    expect(await screen.findByText('Insufficient data')).toBeInTheDocument();
    // A real numeric rate is rendered as a percentage, not the sentinel.
    expect(screen.getByText('33%')).toBeInTheDocument();
  });

  it('shows an honest empty state when there are no opportunities', async () => {
    fetchBoardMock.mockResolvedValue({ columns: [], total: 0 });
    fetchAnalyticsMock.mockResolvedValue(makeAnalytics());

    renderWithProviders(<PipelinePage />, { route: '/pipeline' });

    expect(await screen.findByText('No real CRM activity available.')).toBeInTheDocument();
  });
});
