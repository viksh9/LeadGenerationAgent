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
      status: 'CONNECTED' as const,
      detail: 'API key present; awaiting a verified live check.',
      priority: 1,
      commercial_use_status: 'allowed',
      provider: 'Adzuna',
      authentication_type: 'API_KEY_PAIR',
      credential_env_vars: ['ADZUNA_APP_ID', 'ADZUNA_APP_KEY'],
      capabilities: ['jobs', 'companies', 'job_locations'],
      supports_india: true,
      reliability_tier: 'TIER_2',
      documentation_url: 'https://developer.adzuna.com',
      terms_url: 'https://www.adzuna.com/terms',
      connection_status: 'CONNECTED',
      last_checked_at: '2026-09-05T10:00:00Z',
      last_success_at: '2026-09-05T10:00:00Z',
      last_failure_at: null,
      last_error: null,
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
      provider: null,
      authentication_type: 'NONE',
      credential_env_vars: [],
      capabilities: [],
      supports_india: true,
      reliability_tier: null,
      documentation_url: null,
      terms_url: null,
      connection_status: null,
      last_checked_at: null,
      last_success_at: null,
      last_failure_at: null,
      last_error: null,
    },
  ],
  total: 2,
  connected_count: 1,
  configured_count: 1,
  any_connected: true,
  data_mode: 'REAL_ONLY',
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
    // Capability chips render for the source that reports them.
    expect(screen.getByText('jobs')).toBeInTheDocument();
    expect(screen.getByText('companies')).toBeInTheDocument();
    expect(screen.getByText('Planned', { selector: 'span.badge' })).toBeInTheDocument();
    // Live connectivity line + timestamps for the checked source.
    expect(screen.getByText('Connectivity:')).toBeInTheDocument();
    expect(screen.getByText(/^Last successful:/)).toBeInTheDocument();
    // The unchecked source shows the honest "Not yet checked" note.
    expect(screen.getByText('Not yet checked')).toBeInTheDocument();
    // Data mode badge from the list response.
    expect(screen.getByText('Data mode: REAL_ONLY')).toBeInTheDocument();
    expect(fetchSourcesMock).toHaveBeenCalled();
  });

  it('shows a connected status and backend info from /health', async () => {
    getHealthMock.mockResolvedValue(HEALTH);
    renderWithProviders(<SettingsPage />, { route: '/settings' });

    // Scope to the health widget's ConnectionDot (not a source connectivity badge).
    expect(await screen.findByText('Connected', { selector: 'span:not(.badge)' })).toBeInTheDocument();
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
