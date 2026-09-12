import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '@/test/test-utils';
import { ContactOutSection } from './ContactOutSection';

vi.mock('@/services/contactOut', async (importActual) => {
  const actual = await importActual<typeof import('@/services/contactOut')>();
  return { ...actual, fetchContactOutStatus: vi.fn(), testContactOut: vi.fn() };
});

import { fetchContactOutStatus, testContactOut, type ContactOutStatus } from '@/services/contactOut';

const mockStatus = vi.mocked(fetchContactOutStatus);
const mockTest = vi.mocked(testContactOut);

const status = (over: Partial<ContactOutStatus> = {}): ContactOutStatus => ({
  status: 'NOT_CONFIGURED', configured: false, note: 'POC enrichment is not configured.',
  people_search_rate_per_minute: 60, other_rate_per_minute: 1000,
  max_poc_searches_per_opportunity: 3, max_enrichments_per_opportunity: 2, cache_ttl_hours: 168, ...over,
});

describe('ContactOutSection', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows Not configured and hides the test button', async () => {
    mockStatus.mockResolvedValue(status());
    renderWithProviders(<ContactOutSection />);
    expect(await screen.findByText('Not configured')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /test connection/i })).not.toBeInTheDocument();
  });

  it('offers a connection test when configured and runs it', async () => {
    mockStatus.mockResolvedValue(status({ status: 'CONFIGURED', configured: true,
      note: 'ContactOut is configured.' }));
    mockTest.mockResolvedValue({ source_id: 'contactout', connection_status: 'CONNECTED',
      message: 'ok', performed_request: true, checked_at: '2026-09-12T10:00:00' });
    renderWithProviders(<ContactOutSection />);
    const btn = await screen.findByRole('button', { name: /test connection/i });
    await userEvent.click(btn);
    await waitFor(() => expect(mockTest).toHaveBeenCalled());
    expect(await screen.findByText('Connected')).toBeInTheDocument();
  });
});
