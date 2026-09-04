import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { AppRoutes } from './AppRoutes';

describe('routing', () => {
  it('renders the Leads page at /leads', () => {
    renderWithProviders(<AppRoutes />, { route: '/leads' });
    // The page heading (h2); the header also shows the section title (h1).
    expect(screen.getByRole('heading', { level: 2, name: /^leads$/i })).toBeInTheDocument();
    expect(screen.getByText(/coming next/i)).toBeInTheDocument();
  });

  it('renders a Not Found page for unknown routes', () => {
    renderWithProviders(<AppRoutes />, { route: '/nope' });
    expect(screen.getByText('404')).toBeInTheDocument();
  });

  it('redirects the root route to the dashboard', () => {
    renderWithProviders(<AppRoutes />, { route: '/' });
    expect(
      screen.getByRole('heading', { name: /lead intelligence dashboard/i }),
    ).toBeInTheDocument();
  });
});
