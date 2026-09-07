import { useQuery } from '@tanstack/react-query';
import { getHealth } from '@/services/health';

/** Backend connection status (GET /health). */
export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    retry: false,
    staleTime: 30_000,
  });
}
