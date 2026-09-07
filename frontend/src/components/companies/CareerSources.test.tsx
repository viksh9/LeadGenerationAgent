import { screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { CareerSources } from './CareerSources';
import type { CompanyIntelligence } from '@/types/company';
import type { CareerSource } from '@/services/careerSources';

// Keep display helpers real; only stub the network fetch.
vi.mock('@/services/careerSources', async () => {
  const actual = await vi.importActual<typeof import('@/services/careerSources')>(
    '@/services/careerSources',
  );
  return { ...actual, fetchCareerSources: vi.fn() };
});
import { fetchCareerSources } from '@/services/careerSources';
const fetchMock = vi.mocked(fetchCareerSources);

function makeSource(p: Partial<CareerSource> & Pick<CareerSource, 'id'>): CareerSource {
  return {
    company_id: null,
    company_name: 'Acme Corp',
    ats_provider: 'GREENHOUSE',
    board_identifier: 'acme',
    careers_url: 'https://boards.greenhouse.io/acme',
    discovery_method: 'DNS',
    status: 'CONNECTED',
    enabled: true,
    evidence_tier: 'TIER_1',
    last_checked_at: '2026-09-01T00:00:00Z',
    last_success_at: '2026-09-01T00:00:00Z',
    last_error: null,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
    ...p,
  };
}

// Only company.name is read by the component.
const company = { name: 'Acme Corp' } as CompanyIntelligence;

afterEach(() => vi.clearAllMocks());

describe('CareerSources', () => {
  it('renders a career source matched by company name (case-insensitive)', async () => {
    fetchMock.mockResolvedValue({
      items: [makeSource({ id: 1, company_name: 'acme corp' })],
      total: 1,
    });
    renderWithProviders(<CareerSources company={company} />);

    expect(await screen.findByText('Greenhouse')).toBeInTheDocument();
    expect(screen.getByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('acme')).toBeInTheDocument();
    expect(screen.getByText('Direct official source · TIER_1')).toBeInTheDocument();
  });

  it('shows an honest empty note when no source matches', async () => {
    fetchMock.mockResolvedValue({
      items: [makeSource({ id: 2, company_name: 'Someone Else' })],
      total: 1,
    });
    renderWithProviders(<CareerSources company={company} />);

    expect(await screen.findByText('No official career source discovered yet.')).toBeInTheDocument();
  });
});
