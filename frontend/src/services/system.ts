import { api } from './api';
import type { HealthInfo } from '@/types/settings';

/** Backend health/info (GET /health). */
export async function getHealth(): Promise<HealthInfo> {
  const { data } = await api.get<HealthInfo>('/health');
  return data;
}
