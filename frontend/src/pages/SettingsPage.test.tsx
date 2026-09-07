import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { SettingsPage } from './SettingsPage';
import { getPreferences } from '@/services/preferences';

vi.mock('@/services/health', () => ({ getHealth: vi.fn() }));
import { getHealth } from '@/services/health';
const getHealthMock = vi.mocked(getHealth);

const HEALTH = {
  status: 'healthy',
  app: 'LeadGenerationAgent',
  environment: 'development',
  version: '0.1.0',
};

beforeEach(() => {
  getHealthMock.mockReset();
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
