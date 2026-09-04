import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from './App';

describe('App', () => {
  it('renders and redirects the root route to the dashboard', async () => {
    render(<App />);
    expect(
      await screen.findByRole('heading', { name: /lead intelligence dashboard/i }),
    ).toBeInTheDocument();
  });
});
