import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderOptions } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { ToastProvider } from '@/contexts/ToastContext';

function makeClient() {
  return new QueryClient({
    // gcTime: 0 removes queries as soon as a test's tree unmounts, so in-flight
    // fetches don't bleed across tests. queryCache.onError swallows expected
    // errors so they aren't surfaced as unhandled rejections.
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
    queryCache: new QueryCache({ onError: () => {} }),
    mutationCache: new MutationCache({ onError: () => {} }),
  });
}

export function renderWithProviders(
  ui: ReactElement,
  { route = '/', ...options }: RenderOptions & { route?: string } = {},
) {
  const client = makeClient();
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <ThemeProvider>
          <ToastProvider>
            <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
          </ToastProvider>
        </ThemeProvider>
      </QueryClientProvider>
    );
  }
  return render(ui, { wrapper: Wrapper, ...options });
}
