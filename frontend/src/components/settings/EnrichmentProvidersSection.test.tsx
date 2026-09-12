import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '@/test/test-utils';
import { EnrichmentProvidersSection } from './EnrichmentProvidersSection';

vi.mock('@/services/enrichmentProviders', async (importActual) => {
  const actual = await importActual<typeof import('@/services/enrichmentProviders')>();
  return { ...actual, fetchEnrichmentStatus: vi.fn(), testEnrichmentProvider: vi.fn() };
});

import {
  fetchEnrichmentStatus,
  testEnrichmentProvider,
  type EnrichmentStatus,
} from '@/services/enrichmentProviders';

const mockStatus = vi.mocked(fetchEnrichmentStatus);
const mockTest = vi.mocked(testEnrichmentProvider);

const status = (): EnrichmentStatus => ({
  providers: [
    { provider: 'contactout', status: 'NOT_CONFIGURED', capabilities: { decision_maker_search: true } },
    { provider: 'apollo', status: 'CONFIGURED', capabilities: { person_search: true, person_enrichment: true } },
    { provider: 'hunter', status: 'NOT_CONFIGURED', capabilities: { email_verification: true } },
  ],
});

describe('EnrichmentProvidersSection', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lists providers with config state and only offers a test on configured ones', async () => {
    mockStatus.mockResolvedValue(status());
    renderWithProviders(<EnrichmentProvidersSection />);
    expect(await screen.findByText('Apollo')).toBeInTheDocument();
    expect(screen.getByText('ContactOut')).toBeInTheDocument();
    // Exactly one configured provider (Apollo) → exactly one Test button.
    expect(screen.getAllByRole('button', { name: /^test$/i })).toHaveLength(1);
  });

  it('runs a real connectivity test for a configured provider', async () => {
    mockStatus.mockResolvedValue(status());
    mockTest.mockResolvedValue({ provider: 'apollo', result: 'LIVE_VERIFIED', message: 'ok',
      performed_request: true, checked_at: '2026-09-12T10:00:00' });
    renderWithProviders(<EnrichmentProvidersSection />);
    const btn = await screen.findByRole('button', { name: /^test$/i });
    await userEvent.click(btn);
    await waitFor(() => expect(mockTest).toHaveBeenCalledWith('apollo'));
    expect(await screen.findByText('Live verified')).toBeInTheDocument();
  });
});
