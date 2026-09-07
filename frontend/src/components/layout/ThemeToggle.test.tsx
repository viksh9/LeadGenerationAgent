import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { ThemeToggle } from './ThemeToggle';

afterEach(() => {
  document.documentElement.classList.remove('dark');
  localStorage.clear();
});

describe('ThemeToggle', () => {
  it('toggles the dark class on the document', async () => {
    renderWithProviders(<ThemeToggle />);

    await userEvent.click(screen.getByRole('button', { name: /switch to dark theme/i }));
    expect(document.documentElement.classList.contains('dark')).toBe(true);

    await userEvent.click(screen.getByRole('button', { name: /switch to light theme/i }));
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });
});
