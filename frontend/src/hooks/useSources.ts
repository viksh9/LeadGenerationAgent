import { useQuery } from '@tanstack/react-query';
import { fetchSources } from '@/services/sources';

/** Real source-connectivity states from the backend registry (GET /sources). */
export function useSources() {
  const query = useQuery({
    queryKey: ['sources'],
    queryFn: fetchSources,
    retry: false,
    staleTime: 30_000,
  });

  return {
    data: query.data,
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: query.refetch,
  };
}
