import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { TendersPage } from './TendersPage';
import type { Tender, TenderList } from '@/services/tenders';

// Keep display helpers real; only stub the network fetch.
vi.mock('@/services/tenders', async () => {
  const actual = await vi.importActual<typeof import('@/services/tenders')>('@/services/tenders');
  return { ...actual, fetchTenders: vi.fn(), fetchTender: vi.fn() };
});
import { fetchTenders } from '@/services/tenders';
const fetchMock = vi.mocked(fetchTenders);

function makeTender(p: Partial<Tender> & Pick<Tender, 'id'>): Tender {
  return {
    source_id: 'gem',
    source_record_id: 'rec-1',
    title: 'Core banking modernization',
    organization_name: 'State Bank',
    department: 'IT',
    organization_type: 'PUBLIC',
    location: 'Mumbai',
    issue_date: '2026-08-01T00:00:00Z',
    publication_date: '2026-08-05T00:00:00Z',
    closing_date: '2026-09-30T00:00:00Z',
    award_date: null,
    estimated_value: null,
    currency: null,
    estimated_value_text: null,
    category: 'IT Services',
    technologies: ['Java'],
    scope_summary: 'Modernize the core banking platform.',
    tender_status: 'OPEN',
    source_url: 'https://tenders.example/1',
    company_id: null,
    target_company_id: null,
    signal_origin_organization: null,
    evidence_confidence: 70,
    freshness_score: 90,
    commercial_intent: 'HIGH',
    data_provenance: 'REAL',
    first_seen_at: '2026-08-05T00:00:00Z',
    last_seen_at: '2026-09-01T00:00:00Z',
    ...p,
  };
}

function list(items: Tender[]): TenderList {
  return { items, total: items.length, page: 1, page_size: 20, total_pages: 1 };
}

afterEach(() => vi.clearAllMocks());

describe('TendersPage', () => {
  it('renders a tender row and shows "Not disclosed" for a null value', async () => {
    fetchMock.mockResolvedValue(list([makeTender({ id: 't1' })]));
    renderWithProviders(<TendersPage />);

    expect(await screen.findByText('Core banking modernization')).toBeInTheDocument();
    expect(screen.getByText('State Bank • IT')).toBeInTheDocument();
    // "Open" also appears as a filter option, so scope to the status badge.
    expect(screen.getByText('Open', { selector: 'span.badge' })).toBeInTheDocument();
    expect(screen.getByText('Not disclosed')).toBeInTheDocument();
  });

  it('shows an honest empty state', async () => {
    fetchMock.mockResolvedValue(list([]));
    renderWithProviders(<TendersPage />);

    expect(await screen.findByText('No tenders available yet.')).toBeInTheDocument();
  });

  it('shows an error state', async () => {
    fetchMock.mockRejectedValue(new Error('boom'));
    renderWithProviders(<TendersPage />);

    expect(await screen.findByText(/unable to load tenders/i)).toBeInTheDocument();
  });
});
