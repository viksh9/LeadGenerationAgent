import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '@/test/test-utils';
import { LeadActionBar } from './LeadActionBar';

vi.mock('@/services/crm', async (importActual) => {
  const actual = await importActual<typeof import('@/services/crm')>();
  return { ...actual, transitionLead: vi.fn() };
});
vi.mock('@/services/outreachApi', async (importActual) => {
  const actual = await importActual<typeof import('@/services/outreachApi')>();
  return { ...actual, generateDraft: vi.fn() };
});

import { transitionLead } from '@/services/crm';
import { generateDraft } from '@/services/outreachApi';

const mockTransition = vi.mocked(transitionLead);
const mockDraft = vi.mocked(generateDraft);

describe('LeadActionBar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockTransition.mockResolvedValue({ id: 1, lead_id: 1, new_status: 'RESEARCHED', changed_by: 'human', created_at: '' } as never);
    mockDraft.mockResolvedValue({ id: 9, status: 'READY_FOR_REVIEW' } as never);
  });

  it('marks the lead reviewed via the validated transition endpoint', async () => {
    renderWithProviders(<LeadActionBar leadId={1} status="NEW" />);
    await userEvent.click(screen.getByRole('button', { name: /mark reviewed/i }));
    await waitFor(() => expect(mockTransition).toHaveBeenCalledWith(1, { new_status: 'RESEARCHED' }));
  });

  it('prepares an outreach draft', async () => {
    renderWithProviders(<LeadActionBar leadId={1} status="NEW" />);
    await userEvent.click(screen.getByRole('button', { name: /prepare outreach/i }));
    await waitFor(() => expect(mockDraft).toHaveBeenCalledWith({ lead_id: 1 }));
  });

  it('requires a reason to disqualify (dialog) and sends it', async () => {
    renderWithProviders(<LeadActionBar leadId={1} status="NEW" />);
    await userEvent.click(screen.getByRole('button', { name: /disqualify/i }));
    // Dialog appears with a reason selector; confirm.
    const dialog = await screen.findByRole('dialog', { name: /disqualify lead/i });
    await userEvent.click(within(dialog).getByRole('button', { name: /^disqualify$/i }));
    await waitFor(() =>
      expect(mockTransition).toHaveBeenCalledWith(1, { new_status: 'DISQUALIFIED', reason: 'Not relevant' }));
  });
});
