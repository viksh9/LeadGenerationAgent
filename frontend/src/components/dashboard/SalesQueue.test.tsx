import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';

import { renderWithProviders } from '@/test/test-utils';
import { SalesQueue } from './SalesQueue';

vi.mock('@/services/crm', async (importActual) => {
  const actual = await importActual<typeof import('@/services/crm')>();
  return { ...actual, fetchFollowUps: vi.fn() };
});
vi.mock('@/services/leads', async (importActual) => {
  const actual = await importActual<typeof import('@/services/leads')>();
  return { ...actual, getLeads: vi.fn() };
});

import { fetchFollowUps } from '@/services/crm';
import { getLeads } from '@/services/leads';

const mockFollow = vi.mocked(fetchFollowUps);
const mockLeads = vi.mocked(getLeads);

describe('SalesQueue', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows honest empty states when nothing needs attention', async () => {
    mockFollow.mockResolvedValue({ items: [], total: 0 });
    mockLeads.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 5, total_pages: 0 } as never);
    renderWithProviders(<SalesQueue />);
    expect(await screen.findByText('No follow-ups are due.')).toBeInTheDocument();
    expect(await screen.findByText('No leads need attention.')).toBeInTheDocument();
  });

  it('lists real follow-ups and high-priority leads', async () => {
    mockFollow.mockResolvedValue({ items: [
      { id: 1, lead_id: 7, title: 'Call Infosys', task_type: 'FOLLOW_UP', status: 'OPEN', created_by: 'human', created_at: '', due_at: null },
    ], total: 1 } as never);
    mockLeads.mockResolvedValue({ items: [
      { id: 7, company_name: 'Infosys Ltd', lead_priority: 'HOT' },
    ], total: 1, page: 1, page_size: 5, total_pages: 1 } as never);
    renderWithProviders(<SalesQueue />);
    expect(await screen.findByText('Call Infosys')).toBeInTheDocument();
    expect(await screen.findByText('Infosys Ltd')).toBeInTheDocument();
  });
});
