import { useMutation, useQuery } from '@tanstack/react-query';
import {
  fetchEnrichmentStatus,
  testEnrichmentProvider,
  providerLabel,
  type ProviderTestResponse,
} from '@/services/enrichmentProviders';
import { useToast } from '@/contexts/ToastContext';
import type { ApiErrorShape } from '@/services/api';

const errText = (e: unknown, fallback: string): string =>
  (e as ApiErrorShape | undefined)?.message ?? fallback;

/** Enrichment provider config status + capabilities (Settings). No keys returned. */
export function useEnrichmentStatus() {
  return useQuery({
    queryKey: ['enrichment', 'status'],
    queryFn: ({ signal }) => fetchEnrichmentStatus(signal),
    retry: false,
    staleTime: 60_000,
  });
}

/** Real per-provider connectivity test (no bulk enrichment credits). */
export function useTestEnrichmentProvider() {
  const toast = useToast();
  return useMutation<ProviderTestResponse, unknown, string>({
    mutationFn: (provider) => testEnrichmentProvider(provider),
    onSuccess: (res) => {
      const name = providerLabel(res.provider);
      if (res.result === 'LIVE_VERIFIED') toast.success(`${name} connected.`);
      else toast.info(`${name}: ${res.result.replace(/_/g, ' ').toLowerCase()}.`);
    },
    onError: (e) => toast.error(errText(e, 'Connection test failed.')),
  });
}
