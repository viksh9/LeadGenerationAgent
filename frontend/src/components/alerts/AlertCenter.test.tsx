import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { AlertCenter } from './AlertCenter';
import type { Alert } from '@/services/alerts';

// Keep the real display helpers; stub only the network fetchers.
vi.mock('@/services/alerts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/alerts')>();
  return {
    ...actual,
    fetchAlerts: vi.fn(),
    fetchUnreadCount: vi.fn(),
    setAlertStatus: vi.fn(),
  };
});
import { fetchAlerts, fetchUnreadCount, setAlertStatus } from '@/services/alerts';
const fetchAlertsMock = vi.mocked(fetchAlerts);
const fetchUnreadCountMock = vi.mocked(fetchUnreadCount);
const setAlertStatusMock = vi.mocked(setAlertStatus);

function makeAlert(p: Partial<Alert> = {}): Alert {
  return {
    id: 1,
    alert_type: 'NEW_HIGH_INTENT_LEAD',
    severity: 'CRITICAL',
    status: 'NEW',
    title: 'NorthStar Banking is hiring aggressively',
    message: 'Score jumped after a new project award.',
    company_id: 42,
    lead_id: null,
    opportunity_id: null,
    signal_id: null,
    tender_id: null,
    source_id: null,
    evidence_ids: [1, 2],
    link: '/leads/7',
    triggered_at: '2026-09-05T10:00:00Z',
    acknowledged_at: null,
    resolved_at: null,
    ...p,
  };
}

beforeEach(() => {
  fetchAlertsMock.mockReset();
  fetchUnreadCountMock.mockReset();
  setAlertStatusMock.mockReset();
  fetchUnreadCountMock.mockResolvedValue({ unread_count: 3 });
  fetchAlertsMock.mockResolvedValue({
    items: [
      makeAlert(),
      makeAlert({ id: 2, severity: 'LOW', title: 'Adzuna source is back online', alert_type: 'SOURCE_RECOVERED' }),
    ],
    total: 2,
    unread_count: 3,
  });
  setAlertStatusMock.mockResolvedValue(makeAlert({ status: 'ACKNOWLEDGED' }));
});
afterEach(() => vi.clearAllMocks());

describe('AlertCenter', () => {
  it('shows the unread count on the bell', async () => {
    renderWithProviders(<AlertCenter />);
    expect(await screen.findByLabelText('3 unread alerts')).toBeInTheDocument();
  });

  it('renders alert titles and severity when opened', async () => {
    renderWithProviders(<AlertCenter />);
    await screen.findByLabelText('3 unread alerts');

    await userEvent.click(screen.getByRole('button', { name: 'Notifications' }));

    expect(await screen.findByText('NorthStar Banking is hiring aggressively')).toBeInTheDocument();
    expect(screen.getByText('Adzuna source is back online')).toBeInTheDocument();
    // Severity badges render with their human labels (colour + label).
    expect(screen.getByText('Critical')).toBeInTheDocument();
    expect(screen.getByText('Low')).toBeInTheDocument();
  });

  it('acknowledges an alert via setAlertStatus', async () => {
    renderWithProviders(<AlertCenter />);
    await screen.findByLabelText('3 unread alerts');
    await userEvent.click(screen.getByRole('button', { name: 'Notifications' }));
    await screen.findByText('NorthStar Banking is hiring aggressively');

    const [acknowledge] = screen.getAllByRole('button', { name: /acknowledge/i });
    await userEvent.click(acknowledge);

    await waitFor(() =>
      expect(setAlertStatusMock).toHaveBeenCalledWith(1, 'ACKNOWLEDGED'),
    );
  });

  it('shows an empty state when there are no alerts', async () => {
    fetchUnreadCountMock.mockResolvedValue({ unread_count: 0 });
    fetchAlertsMock.mockResolvedValue({ items: [], total: 0, unread_count: 0 });
    renderWithProviders(<AlertCenter />);

    await userEvent.click(screen.getByRole('button', { name: 'Notifications' }));
    expect(await screen.findByText('No alerts')).toBeInTheDocument();
  });
});
