import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '@/test/test-utils';
import { SalesActivityCard } from './SalesActivityCard';

vi.mock('@/services/crm', async (importActual) => {
  const actual = await importActual<typeof import('@/services/crm')>();
  return { ...actual, fetchLeadActivities: vi.fn(), createActivity: vi.fn(), createLeadFollowUp: vi.fn() };
});

import { fetchLeadActivities, createActivity, createLeadFollowUp } from '@/services/crm';

const mockList = vi.mocked(fetchLeadActivities);
const mockCreate = vi.mocked(createActivity);
const mockFollow = vi.mocked(createLeadFollowUp);

describe('SalesActivityCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockList.mockResolvedValue({ items: [], total: 0 });
    mockCreate.mockResolvedValue({ id: 1 } as never);
    mockFollow.mockResolvedValue({ id: 2 } as never);
  });

  it('shows an honest empty state when no activity is recorded', async () => {
    renderWithProviders(<SalesActivityCard leadId={1} />);
    expect(await screen.findByText('No sales activity recorded.')).toBeInTheDocument();
  });

  it('logs a real activity with the entered note', async () => {
    renderWithProviders(<SalesActivityCard leadId={1} />);
    await userEvent.type(screen.getByPlaceholderText(/what happened/i), 'Called engineering lead');
    await userEvent.click(screen.getByRole('button', { name: /log activity/i }));
    await waitFor(() => expect(mockCreate).toHaveBeenCalled());
    expect(mockCreate.mock.calls[0][0]).toMatchObject({ lead_id: 1, activity_type: 'NOTE', body_reference: 'Called engineering lead' });
  });

  it('creates a follow-up with the entered title', async () => {
    renderWithProviders(<SalesActivityCard leadId={1} />);
    await userEvent.type(screen.getByPlaceholderText(/call next tuesday/i), 'Follow up Friday');
    await userEvent.click(screen.getByRole('button', { name: /add follow-up/i }));
    await waitFor(() => expect(mockFollow).toHaveBeenCalledWith(1, expect.objectContaining({ title: 'Follow up Friday' })));
  });
});
