import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { SignalsPage } from './SignalsPage';
import type { Signal, SignalList } from '@/services/signals';

// Keep display helpers real; only stub the network fetch.
vi.mock('@/services/signals', async () => {
  const actual = await vi.importActual<typeof import('@/services/signals')>('@/services/signals');
  return { ...actual, fetchSignals: vi.fn(), fetchSignal: vi.fn() };
});
import { fetchSignals } from '@/services/signals';
const fetchMock = vi.mocked(fetchSignals);

function makeSignal(p: Partial<Signal> & Pick<Signal, 'id'>): Signal {
  return {
    company_id: null,
    company_name: 'Acme Corp',
    signal_type: 'HIRING',
    signal_title: 'Scaling the platform team',
    signal_description: 'Hiring several backend engineers.',
    signal_url: 'https://news.example/acme',
    published_at: '2026-09-01T00:00:00Z',
    technologies: ['Java', 'AWS'],
    location: 'Pune',
    signal_strength: 'STRONG',
    source_id: 'press_release',
    source_count: 2,
    evidence_confidence: 82,
    commercial_intent: 'HIGH',
    data_provenance: 'REAL',
    ...p,
  };
}

function list(items: Signal[]): SignalList {
  return { items, total: items.length, page: 1, page_size: 20, total_pages: 1 };
}

afterEach(() => vi.clearAllMocks());

describe('SignalsPage', () => {
  it('renders a signal row from fetched data', async () => {
    fetchMock.mockResolvedValue(list([makeSignal({ id: 's1' })]));
    renderWithProviders(<SignalsPage />);

    expect(await screen.findByText('Scaling the platform team')).toBeInTheDocument();
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText('Strong')).toBeInTheDocument();
    expect(screen.getByText('High')).toBeInTheDocument();
  });

  it('shows an honest empty state', async () => {
    fetchMock.mockResolvedValue(list([]));
    renderWithProviders(<SignalsPage />);

    expect(await screen.findByText('No verified signals available yet.')).toBeInTheDocument();
  });

  it('shows an error state', async () => {
    fetchMock.mockRejectedValue(new Error('boom'));
    renderWithProviders(<SignalsPage />);

    expect(await screen.findByText(/unable to load business signals/i)).toBeInTheDocument();
  });
});
