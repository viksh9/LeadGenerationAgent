import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';

import { renderWithProviders } from '@/test/test-utils';
import { SourceCoverage } from './SourceCoverage';

vi.mock('@/services/sources', async () => {
  const actual = await vi.importActual<typeof import('@/services/sources')>('@/services/sources');
  return { ...actual, fetchSources: vi.fn() };
});

import { fetchSources } from '@/services/sources';
const mockFetch = vi.mocked(fetchSources);

function makeItem(over: Record<string, unknown> = {}) {
  return {
    source_id: 'adzuna', name: 'Adzuna', category: 'JOB', source_type: 'API',
    collector_implemented: true, requires_api_key: true, status: 'CONNECTED', detail: '',
    priority: 2, commercial_use_status: 'REQUIRES_REVIEW', provider: 'Adzuna',
    authentication_type: 'API_KEY', credential_env_vars: [], capabilities: [], supports_india: true,
    reliability_tier: 'TIER_2', documentation_url: null, terms_url: null,
    connection_status: 'CONNECTED', last_checked_at: null, last_success_at: '2026-09-08T05:00:00',
    last_failure_at: null, last_error: null, last_ingestion_at: null,
    last_ingestion_records_fetched: 19, last_ingestion_records_persisted: 8, ...over,
  };
}

describe('SourceCoverage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders real source rows with connection status and counts', async () => {
    mockFetch.mockResolvedValue({
      items: [makeItem(), makeItem({ source_id: 'jooble', name: 'Jooble', status: 'NOT_CONFIGURED',
        connection_status: null, last_success_at: null, last_ingestion_records_persisted: null })],
      total: 2, connected_count: 1, configured_count: 1, any_connected: true, data_mode: 'REAL_ONLY',
    });
    renderWithProviders(<SourceCoverage />);
    expect(await screen.findByText('Adzuna')).toBeInTheDocument();
    expect(screen.getByText('Jooble')).toBeInTheDocument();
    expect(screen.getByText(/1 connected/)).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument(); // records persisted for adzuna
  });

  it('shows an honest empty state when no sources are registered', async () => {
    mockFetch.mockResolvedValue({
      items: [], total: 0, connected_count: 0, configured_count: 0, any_connected: false,
      data_mode: 'REAL_ONLY',
    });
    renderWithProviders(<SourceCoverage />);
    expect(await screen.findByText(/No data sources registered/i)).toBeInTheDocument();
  });
});
