import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { OutreachWorkspace } from './OutreachWorkspace';
import type { OutreachDraft, OutreachDraftList, ProviderStatus } from '@/services/outreachApi';

// Keep the real display helpers; stub only the network fetchers.
vi.mock('@/services/outreachApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/outreachApi')>();
  return {
    ...actual,
    fetchDrafts: vi.fn(),
    fetchProviderStatus: vi.fn(),
  };
});
import { fetchDrafts, fetchProviderStatus } from '@/services/outreachApi';
const fetchDraftsMock = vi.mocked(fetchDrafts);
const fetchProviderStatusMock = vi.mocked(fetchProviderStatus);

function makeDraft(p: Partial<OutreachDraft> = {}): OutreachDraft {
  return {
    id: 1,
    lead_id: 7,
    company_id: 10,
    contact_id: null,
    target_role: 'VP of Engineering',
    channel: 'EMAIL',
    subject: 'Scaling your team',
    message: 'We noticed your recent project award…',
    evidence_ids: [1, 2],
    ai_generated: true,
    grounding_ok: true,
    confidence: 62,
    status: 'DRAFT',
    recipient_email: null,
    provider: null,
    provider_message_id: null,
    error: null,
    created_by: 'system',
    approved_by: null,
    created_at: '2026-09-01T00:00:00Z',
    approved_at: null,
    sent_at: null,
    ...p,
  };
}

const NOT_CONFIGURED: ProviderStatus = {
  email_provider: null,
  email_status: 'NOT_CONFIGURED',
  email_from: null,
  crm_provider: 'internal',
  crm_status: 'CONFIGURED',
  webhook_configured: false,
  note: 'No email provider configured.',
};

function list(items: OutreachDraft[]): OutreachDraftList {
  return { items, total: items.length };
}

beforeEach(() => {
  fetchDraftsMock.mockReset();
  fetchProviderStatusMock.mockReset();
  fetchProviderStatusMock.mockResolvedValue(NOT_CONFIGURED);
});
afterEach(() => vi.clearAllMocks());

describe('OutreachWorkspace', () => {
  it('renders a DRAFT card in the Needs Review tab', async () => {
    fetchDraftsMock.mockResolvedValue(list([makeDraft()]));
    renderWithProviders(<OutreachWorkspace />, { route: '/outreach' });

    expect(await screen.findByText('Scaling your team')).toBeInTheDocument();
    expect(screen.getByText('We noticed your recent project award…')).toBeInTheDocument();
    expect(screen.getByText(/VP of Engineering/)).toBeInTheDocument();
  });

  it('disables Approve and shows a grounding warning when grounding_ok is false', async () => {
    fetchDraftsMock.mockResolvedValue(list([makeDraft({ grounding_ok: false })]));
    renderWithProviders(<OutreachWorkspace />, { route: '/outreach' });

    await screen.findByText('Scaling your team');
    expect(
      screen.getByText(/not evidence-grounded — add evidence before approving/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
  });

  it('disables Send when the email provider is NOT_CONFIGURED', async () => {
    fetchDraftsMock.mockResolvedValue(list([makeDraft({ status: 'APPROVED' })]));
    renderWithProviders(<OutreachWorkspace />, { route: '/outreach' });

    // Provider banner surfaces the honest not-configured message.
    expect(
      await screen.findByText(/email provider not configured — drafts can be approved but not sent/i),
    ).toBeInTheDocument();

    // The APPROVED draft lives in the "Ready to Send" tab.
    await userEvent.click(screen.getByRole('tab', { name: /ready to send/i }));
    const send = screen.getByRole('button', { name: 'Send' });
    expect(send).toBeDisabled();
  });

  it('enables Send for an APPROVED draft when the provider is configured', async () => {
    fetchProviderStatusMock.mockResolvedValue({
      ...NOT_CONFIGURED,
      email_provider: 'smtp',
      email_status: 'CONFIGURED',
      email_from: 'sales@example.com',
    });
    fetchDraftsMock.mockResolvedValue(list([makeDraft({ status: 'APPROVED' })]));
    renderWithProviders(<OutreachWorkspace />, { route: '/outreach' });

    await screen.findByRole('tab', { name: /ready to send/i });
    await userEvent.click(screen.getByRole('tab', { name: /ready to send/i }));
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  });

  it('shows an honest empty state in the Sent tab when nothing is sent', async () => {
    fetchDraftsMock.mockResolvedValue(list([makeDraft()]));
    renderWithProviders(<OutreachWorkspace />, { route: '/outreach' });

    await screen.findByText('Scaling your team');
    await userEvent.click(screen.getByRole('tab', { name: /^sent/i }));
    expect(screen.getByText('No sales activity recorded.')).toBeInTheDocument();
  });
});
