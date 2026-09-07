import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { Sidebar } from './Sidebar';

describe('Sidebar', () => {
  it('renders the app name and all navigation items', () => {
    renderWithProviders(<Sidebar open={false} onClose={() => {}} />, { route: '/dashboard' });

    expect(screen.getByText('LeadGenerationAgent')).toBeInTheDocument();

    const nav = screen.getByRole('navigation', { name: /primary/i });
    for (const label of ['Dashboard', 'Leads', 'Companies', 'Opportunities', 'Contacts', 'Outreach', 'Analytics', 'Monitoring', 'Settings']) {
      expect(within(nav).getByRole('link', { name: label })).toBeInTheDocument();
    }
  });
});
