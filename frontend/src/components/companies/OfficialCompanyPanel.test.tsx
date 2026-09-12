import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';

import { renderWithProviders } from '@/test/test-utils';
import { OfficialCompanyPanel } from './OfficialCompanyPanel';
import type { CompanyPublicIntelligence } from '@/services/publicIntelligence';

vi.mock('@/services/companies', () => ({ searchCompanies: vi.fn() }));
vi.mock('@/services/publicIntelligence', async (importActual) => {
  const actual = await importActual<typeof import('@/services/publicIntelligence')>();
  return { ...actual, fetchCompanyPublicIntelligence: vi.fn(), discoverCompanyPublicIntelligence: vi.fn() };
});

import { searchCompanies } from '@/services/companies';
import { fetchCompanyPublicIntelligence } from '@/services/publicIntelligence';

const mockSearch = vi.mocked(searchCompanies);
const mockFetch = vi.mocked(fetchCompanyPublicIntelligence);

const profile: CompanyPublicIntelligence = {
  company_id: 1, company_name: 'Acme', website: 'https://acme.com', linkedin_url: 'https://linkedin.com/company/acme',
  industry: 'IT', city: 'Bengaluru', state: 'Karnataka', country: 'India',
  full_address: '12 MG Road, Bengaluru, Karnataka, India', postal_code: '560001',
  company_phone: '+91-80-1', company_email: 'info@acme.com', contact_url: 'https://acme.com/contact',
  careers_url: 'https://acme.com/careers', leadership_url: null, wikidata_id: null,
  legal_name: 'Acme Limited', company_number: 'L123', jurisdiction_code: 'in_ka',
  company_status: 'ACTIVE', incorporation_date: null, registry_url: 'https://mca.gov.in/x',
  opencorporates_url: 'https://opencorporates.com/companies/in_ka/L123',
  registered_address: '99 Registry Rd, Bengaluru', india_entity_type: 'INDIA_ENTITY',
  data_trust_score: 100, official_verified_at: '2026-09-12T10:00:00', india_locations: [],
  locations: [], officers: [], public_leadership: [],
  field_sources: [{ field: 'address', value: '12 MG Road', source: 'Official Company Contact Page',
    source_type: 'company_contact_page', source_url: 'https://acme.com/contact', evidence_text: null,
    trust_score: 95, retrieved_at: '2026-09-12T10:00:00' }],
};

describe('OfficialCompanyPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSearch.mockResolvedValue([{ id: 1, canonical_name: 'Acme' } as never]);
  });

  it('shows real website, address, trust and a clickable source URL', async () => {
    mockFetch.mockResolvedValue(profile);
    renderWithProviders(<OfficialCompanyPanel companyName="Acme" />);
    expect(await screen.findByText('12 MG Road, Bengaluru, Karnataka, India')).toBeInTheDocument();
    expect(screen.getByText(/Data Trust: 100%/)).toBeInTheDocument();
    // Source link is clickable and uses the exact stored URL (§33).
    const link = screen.getAllByRole('link', { name: /source/i })[0];
    expect(link).toHaveAttribute('href', 'https://acme.com/contact');
  });

  it('shows "Not Publicly Available" for missing fields, never fabricated', async () => {
    mockFetch.mockResolvedValue({ ...profile, company_phone: null, company_email: null });
    renderWithProviders(<OfficialCompanyPanel companyName="Acme" />);
    expect(await screen.findAllByText('Not Publicly Available')).toBeTruthy();
  });

  it('shows an honest empty state when there is no company entity', async () => {
    mockFetch.mockResolvedValue(null as never);
    mockSearch.mockResolvedValue([]);
    renderWithProviders(<OfficialCompanyPanel companyName="Nope" />);
    expect(await screen.findByText(/No verified company entity yet/i)).toBeInTheDocument();
  });
});
