import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  discoverLeadPocs,
  enrichPoc,
  fetchContactOutStatus,
  fetchLeadPocs,
  testContactOut,
  type ConnectionTestResult,
  type POCDiscovery,
} from '@/services/contactOut';
import { discoverPublicIntelligence } from '@/services/publicIntelligence';
import { useToast } from '@/contexts/ToastContext';
import type { ApiErrorShape } from '@/services/api';

const errText = (e: unknown, fallback: string): string =>
  (e as ApiErrorShape | undefined)?.message ?? fallback;

export const pocKeys = {
  lead: (leadId: number) => ['pocs', 'lead', leadId] as const,
  status: ['contactout', 'status'] as const,
};

/** POCs + role recommendations for a lead (GET /leads/{id}/pocs). */
export function useLeadPocs(leadId: number | undefined) {
  return useQuery({
    queryKey: pocKeys.lead(leadId ?? -1),
    queryFn: ({ signal }) => fetchLeadPocs(leadId as number, signal),
    enabled: typeof leadId === 'number' && leadId > 0,
    retry: false,
    staleTime: 30_000,
  });
}

/** Run ContactOut POC discovery for a lead's company. */
export function useDiscoverPocs(leadId: number) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation<POCDiscovery, unknown, { force?: boolean } | void>({
    mutationFn: (args) => discoverLeadPocs(leadId, (args && args.force) || false),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: pocKeys.lead(leadId) });
      const map: Record<string, string> = {
        ENRICHED: `Found ${res.persisted} POC(s) from ContactOut.`,
        CACHED: 'Reused recent ContactOut POC(s).',
        NO_POC_FOUND: 'No verified POC found for this opportunity.',
        NOT_CONFIGURED: 'ContactOut is not configured.',
        RATE_LIMITED: 'ContactOut rate limit reached; try again shortly.',
        UNAVAILABLE: 'ContactOut is unavailable right now.',
      };
      toast.info(map[res.status] ?? res.reason);
    },
    onError: (e) => toast.error(errText(e, 'POC discovery could not run.')),
  });
}

/** Re-enrich a single stored POC. */
export function useEnrichPoc(leadId: number) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation<POCDiscovery, unknown, number>({
    mutationFn: (pocId) => enrichPoc(pocId),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: pocKeys.lead(leadId) });
      toast.info(res.status === 'ENRICHED' ? 'POC re-enriched.' : res.reason);
    },
    onError: (e) => toast.error(errText(e, 'POC enrichment could not run.')),
  });
}

/** ContactOut integration config status (Settings). */
export function useContactOutStatus() {
  return useQuery({
    queryKey: pocKeys.status,
    queryFn: ({ signal }) => fetchContactOutStatus(signal),
    retry: false,
    staleTime: 60_000,
  });
}

/** Discover free/public intelligence (official website, GitHub, Wikidata). */
export function useDiscoverPublicIntelligence(leadId: number) {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (args: { force?: boolean } | void) =>
      discoverPublicIntelligence(leadId, (args && args.force) || false),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: pocKeys.lead(leadId) });
      const map: Record<string, string> = {
        ENRICHED: `Found ${res.persisted} public POC(s).`,
        CACHED: 'Reused recent public POC(s).',
        NO_POC_FOUND: 'No verified public POC found; role recommendations only.',
        DISABLED: 'Public intelligence is disabled.',
      };
      toast.info(map[res.status] ?? res.reason);
    },
    onError: (e) => toast.error(errText(e, 'Public intelligence discovery could not run.')),
  });
}

/** Real connectivity test (no enrichment credits). */
export function useTestContactOut() {
  const toast = useToast();
  return useMutation<ConnectionTestResult, unknown, void>({
    mutationFn: () => testContactOut(),
    onSuccess: (res) => {
      if (res.connection_status === 'CONNECTED') toast.success('ContactOut connected.');
      else toast.info(`ContactOut: ${res.connection_status.replace(/_/g, ' ').toLowerCase()}.`);
    },
    onError: (e) => toast.error(errText(e, 'Connection test failed.')),
  });
}
