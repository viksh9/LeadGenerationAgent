import { useMutation, useQuery } from '@tanstack/react-query';
import {
  discoverCareerSourceByDomain,
  fetchCareerSources,
  type DiscoverByDomainBody,
  type DiscoverResult,
} from '@/services/careerSources';
import { useToast } from '@/contexts/ToastContext';
import type { ApiErrorShape } from '@/services/api';

/** Official career sources registry (GET /career-sources). */
export function useCareerSources() {
  const query = useQuery({
    queryKey: ['career-sources'],
    queryFn: fetchCareerSources,
    retry: false,
    staleTime: 30_000,
  });

  return {
    data: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

const errText = (e: unknown, fallback: string): string =>
  (e as ApiErrorShape | undefined)?.message ?? fallback;

/**
 * Live ATS/career-source discovery from a provided domain / careers URL
 * (POST /career-sources/discover). Returns the real result; never fabricated.
 */
export function useDiscoverCareerSource() {
  const toast = useToast();
  return useMutation<DiscoverResult, unknown, DiscoverByDomainBody>({
    mutationFn: (body) => discoverCareerSourceByDomain(body),
    onError: (e) => toast.error(errText(e, 'Discovery could not run. Check the domain/URL and try again.')),
  });
}
