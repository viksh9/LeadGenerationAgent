/** User preferences persisted in this browser (localStorage) — no backend. */
export interface Preferences {
  leadsPageSize: number;
}

/** Response of GET /health. */
export interface HealthInfo {
  status: string;
  app: string;
  environment: string;
  version: string;
}
