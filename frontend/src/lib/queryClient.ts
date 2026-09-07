import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    // Never auto-retry mutations — create/update/delete/analyze are not
    // idempotent from the user's perspective.
    mutations: {
      retry: 0,
    },
  },
});
