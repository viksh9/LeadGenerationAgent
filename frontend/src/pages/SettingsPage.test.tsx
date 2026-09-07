import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { SettingsPage } from './SettingsPage';
import { getPreferences } from '@/services/preferences';

vi.mock('@/services/health', () => ({ getHealth: vi.fn() }));
import { getHealth } from '@/services/health';
const getHealthMock = vi.mocked(getHealth);

vi.mock('@/services/sources', async () => {
  const actual = await vi.importActual<typeof import('@/services/sources')>('@/services/sources');
  return { ...actual, fetchSources: vi.fn() };
});
import { fetchSources } from '@/services/sources';
const fetchSourcesMock = vi.mocked(fetchSources);

const HEALTH = {
  status: 'healthy',
  app: 'LeadGenerationAgent',
  environment: 'development',
  version: '0.1.0',
};

const SOURCES = {
  items: [
    {
      source_id: 'adzuna',
      name: 'Adzuna Jobs API',
      category: 'Job',
      source_type: 'api',
      collector_implemented: true,
      requires_api_key: true,
      status: 'CONFIGURED' as const,
      detail: 'API key present; awaiting a verified live check.',
      priority: 1,
      commercial_use_status: 'allowed',
    },
    {
      source_id: 'rss_news',
      name: 'RSS / Business & Technology News',
      category: 'News',
      source_type: 'rss',
      collector_implemented: false,
      requires_api_key: false,
      status: 'PLANNED' as const,
      detail: 'Collector not yet implemented.',
      priority: 5,
      commercial_use_status: 'allowed',
    },
  ],
  total: 2,
  connected_count: 1,
  configured_count: 1,
  any_connected: true,
};

beforeEach(() => {
  getHealthMock.mockReset();
  fetchSourcesMock.mockReset();
  fetchSourcesMock.mockResolvedValue(SOURCES);
  localStorage.clear();
});
afterEach(() => {
  document.documentElement.classList.remove('dark');
  vi.clearAllMocks();
});

describe('SettingsPage', () => {
  it('renders the settings sections', async () => {
    getHealthMock.mockResolvedValue(HEALTH);
    renderWithProviders(<SettingsPage />, { route: '/settings' });

    expect(await screen.findByRole('heading', { level: 2, name: 'Settings' })).toBeInTheDocument();
    expect(screen.getByText('Preferences')).toBeInTheDocument();
    expect(screen.getByText('Connection')).toBeInTheDocument();
    expect(screen.getByText('About')).toBeInTheDocument();
  });

  it('renders live source connectivity from /sources', async () => {
    getHealthMock.mockResolvedValue(HEALTH);
    renderWithProviders(<SettingsPage />, { route: '/settings' });

    expect(await screen.findByText('Adzuna Jobs API')).toBeInTheDocument();
    expect(screen.getByText('API key present; awaiting a verified live check.')).toBeInTheDocument();
    expect(screen.getByText('Configured', { selector: 'span.badge' })).toBeInTheDocument();
    expect(screen.getByText('Planned', { selector: 'span.badge' })).toBeInTheDocument();
    expect(fetchSourcesMock).toHaveBeenCalled();
  });

  it('shows a connected status and backend info from /health', async () => {
    getHealthMock.mockResolvedValue(HEALTH);
    renderWithProviders(<SettingsPage />, { route: '/settings' });

    expect(await screen.findByText('Connected')).toBeInTheDocument();
    expect(screen.getByText('development')).toBeInTheDocument();
    expect(screen.getByText('0.1.0')).toBeInTheDocument();
  });

  it('shows an unreachable status when /health fails', async () => {
    getHealthMock.mockResolvedValue(HEALTH);
    getHealthMock.mockRejectedValueOnce(new Error('down'));
    renderWithProviders(<SettingsPage />, { route: '/settings' });

    expect(await screen.findByText('Unreachable')).toBeInTheDocument();
  });

  it('persists the leads-per-page preference', async () => {
    getHealthMock.mockResolvedValue(HEALTH);
    renderWithProviders(<SettingsPage />, { route: '/settings' });
    await screen.findByRole('heading', { level: 2, name: 'Settings' });

    await userEvent.selectOptions(screen.getByLabelText('Leads per page'), '50');
    await waitFor(() => expect(getPreferences().leadsPageSize).toBe(50));
  });

  it('resets preferences to the default', async () => {
    getHealthMock.mockResolvedValue(HEALTH);
    renderWithProviders(<SettingsPage />, { route: '/settings' });
    await screen.findByRole('heading', { level: 2, name: 'Settings' });

    await userEvent.selectOptions(screen.getByLabelText('Leads per page'), '100');
    await waitFor(() => expect(getPreferences().leadsPageSize).toBe(100));

    await userEvent.click(screen.getByRole('button', { name: 'Reset' }));
    await waitFor(() => expect(getPreferences().leadsPageSize).toBe(20));
    expect((screen.getByLabelText('Leads per page') as HTMLSelectElement).value).toBe('20');
  });

  it('changes the theme and applies the dark class', async () => {
    getHealthMock.mockResolvedValue(HEALTH);
    renderWithProviders(<SettingsPage />, { route: '/settings' });
    await screen.findByRole('heading', { level: 2, name: 'Settings' });

    await userEvent.selectOptions(screen.getByLabelText('Theme'), 'dark');
    await waitFor(() => expect(document.documentElement.classList.contains('dark')).toBe(true));
    expect(getPreferences().theme).toBe('dark');
  });

  it('clears cached data with feedback', async () => {
    getHealthMock.mockResolvedValue(HEALTH);
    renderWithProviders(<SettingsPage />, { route: '/settings' });
    await screen.findByRole('heading', { level: 2, name: 'Settings' });

    await userEvent.click(screen.getByRole('button', { name: /clear cache/i }));
    expect(await screen.findByText('Cleared')).toBeInTheDocument();
  });
});
