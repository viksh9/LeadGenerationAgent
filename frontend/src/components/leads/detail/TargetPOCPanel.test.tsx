import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '@/test/test-utils';
import { TargetPOCPanel } from './TargetPOCPanel';

vi.mock('@/services/contactOut', async (importActual) => {
  const actual = await importActual<typeof import('@/services/contactOut')>();
  return { ...actual, fetchLeadPocs: vi.fn(), discoverLeadPocs: vi.fn() };
});

import { fetchLeadPocs, discoverLeadPocs, type POCList } from '@/services/contactOut';

const mockFetch = vi.mocked(fetchLeadPocs);
const mockDiscover = vi.mocked(discoverLeadPocs);

const base: POCList = {
  lead_id: 1, company_name: 'Acme Corp', contactout_status: 'NOT_CONFIGURED',
  pocs: [], recommended_roles: [], recommendation_confidence: 0, note: null,
};

describe('TargetPOCPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows "not configured" and no fabricated people', async () => {
    mockFetch.mockResolvedValue({
      ...base, contactout_status: 'NOT_CONFIGURED', note: 'POC enrichment is not configured.',
      recommended_roles: [{ role: 'Head of Engineering', role_category: 'ENGINEERING',
        decision_maker_type: 'TECHNICAL', relevance_score: 84, reason: 'High tech hiring.', is_primary: true }],
    });
    renderWithProviders(<TargetPOCPanel leadId={1} />);
    expect(await screen.findByText(/POC enrichment is not configured/i)).toBeInTheDocument();
    // Role-only recommendation, never a fake name.
    expect(screen.getByText(/Recommended POC Role/i)).toBeInTheDocument();
    expect(screen.getByText('Head of Engineering')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /discover/i })).not.toBeInTheDocument();
  });

  it('renders a real POC with trust, work email and phone', async () => {
    mockFetch.mockResolvedValue({
      ...base, contactout_status: 'CONFIGURED',
      pocs: [{
        id: 5, company_id: 1, company_name: 'Acme Corp', full_name: 'Jane Doe', job_title: 'VP Engineering',
        seniority: null, company_domain: 'acme.com', professional_network_url: 'https://linkedin.com/in/jane',
        business_email: 'jane@acme.com', business_phone: '+91-80-1234', email_status: 'VERIFIED_SOURCE',
        contact_source: 'ContactOut', source_url: 'https://linkedin.com/in/jane', match_score: 98,
        contact_trust_score: 100, contact_trust_status: 'VERIFIED', is_current: true,
        verification_status: 'VERIFIED', last_verified_at: '2026-09-12T10:00:00',
      }],
    });
    renderWithProviders(<TargetPOCPanel leadId={1} />);
    expect(await screen.findByText('Jane Doe')).toBeInTheDocument();
    expect(screen.getByText('VP Engineering')).toBeInTheDocument();
    expect(screen.getByText('jane@acme.com')).toBeInTheDocument();
    expect(screen.getByText('+91-80-1234')).toBeInTheDocument();
    expect(screen.getByText(/Contact Trust: Verified/i)).toBeInTheDocument();
  });

  it('runs discovery when the button is clicked', async () => {
    mockFetch.mockResolvedValue({ ...base, contactout_status: 'CONFIGURED',
      note: 'No verified POC found for this opportunity yet.' });
    mockDiscover.mockResolvedValue({
      lead_id: 1, company_id: 1, company_name: 'Acme Corp', status: 'NO_POC_FOUND',
      candidates_found: 0, searches_used: 1, enrichments_used: 0, persisted: 0,
      reason: 'No verified POC found for this opportunity.', error_code: null, pocs: [],
    });
    renderWithProviders(<TargetPOCPanel leadId={1} />);
    const btn = await screen.findByRole('button', { name: /discover pocs/i });
    await userEvent.click(btn);
    await waitFor(() => expect(mockDiscover).toHaveBeenCalledWith(1, false));
  });
});
