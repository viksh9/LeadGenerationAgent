import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '@/test/test-utils';
import { CareerIntegrationPage } from './CareerIntegrationPage';

vi.mock('@/services/careerSources', async (importActual) => {
  const actual = await importActual<typeof import('@/services/careerSources')>();
  return { ...actual, discoverCareerSourceByDomain: vi.fn() };
});

import { discoverCareerSourceByDomain } from '@/services/careerSources';

const mockDiscover = vi.mocked(discoverCareerSourceByDomain);

describe('CareerIntegrationPage', () => {
  beforeEach(() => vi.clearAllMocks());

  it('disables Discover until both company and domain/URL are entered', async () => {
    renderWithProviders(<CareerIntegrationPage />);
    const button = screen.getByRole('button', { name: /discover/i });
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/company name/i), 'EPAM Systems');
    expect(button).toBeDisabled(); // still needs a domain/URL
    await userEvent.type(screen.getByLabelText(/domain or careers url/i), 'epam.com');
    expect(button).toBeEnabled();
  });

  it('sends a bare domain as `domain` and shows a found result', async () => {
    mockDiscover.mockResolvedValue({
      company_id: null, company_name: 'EPAM Systems', found: true, verified: true,
      provider: 'GREENHOUSE', board_identifier: 'epam',
      careers_url: 'https://epam.com/careers', discovery_method: 'careers_page_link',
      detail: "Found Greenhouse board 'epam'.",
    });
    renderWithProviders(<CareerIntegrationPage />);
    await userEvent.type(screen.getByLabelText(/company name/i), 'EPAM Systems');
    await userEvent.type(screen.getByLabelText(/domain or careers url/i), 'epam.com');
    await userEvent.click(screen.getByRole('button', { name: /discover/i }));

    await waitFor(() =>
      expect(mockDiscover).toHaveBeenCalledWith({ company_name: 'EPAM Systems', domain: 'epam.com' }),
    );
    expect(await screen.findByText(/source found/i)).toBeInTheDocument();
    expect(screen.getByText(/ownership verified/i)).toBeInTheDocument();
    expect(screen.getByText('Greenhouse')).toBeInTheDocument();
    expect(screen.getByText('epam')).toBeInTheDocument();
  });

  it('sends a full URL as `careers_url` and reports an honest "no source found"', async () => {
    mockDiscover.mockResolvedValue({
      company_id: null, company_name: 'Acme', found: false, verified: false,
      provider: null, board_identifier: null, careers_url: null,
      discovery_method: null, detail: 'No supported ATS detected on the page.',
    });
    renderWithProviders(<CareerIntegrationPage />);
    await userEvent.type(screen.getByLabelText(/company name/i), 'Acme');
    await userEvent.type(screen.getByLabelText(/domain or careers url/i), 'https://acme.com/careers');
    await userEvent.click(screen.getByRole('button', { name: /discover/i }));

    await waitFor(() =>
      expect(mockDiscover).toHaveBeenCalledWith({
        company_name: 'Acme', careers_url: 'https://acme.com/careers',
      }),
    );
    expect(await screen.findByText(/no source found/i)).toBeInTheDocument();
    expect(screen.getByText(/no supported ats detected/i)).toBeInTheDocument();
  });
});
