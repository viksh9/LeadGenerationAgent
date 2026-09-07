export type ThemePreference = 'light' | 'dark' | 'system';

/** User preferences persisted in this browser (localStorage) — no backend. */
export interface Preferences {
  leadsPageSize: number;
  theme: ThemePreference;
}

/** Response of GET /health. */
export interface HealthInfo {
  status: string;
  app: string;
  environment: string;
  version: string;
}
