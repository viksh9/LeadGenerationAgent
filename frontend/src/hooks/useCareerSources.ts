import { useQuery } from '@tanstack/react-query';
import { fetchCareerSources } from '@/services/careerSources';

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
