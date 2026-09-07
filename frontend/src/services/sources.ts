import { api } from './api';

/**
 * Real source-connectivity states from the backend registry (GET /sources).
 * A source is only CONNECTED after a verified live check — no source is
 * "connected" merely because a collector exists.
 */
export type SourceStatus =
  | 'CONNECTED'
  | 'CONFIGURED'
  | 'NOT_CONFIGURED'
  | 'AUTHENTICATION_REQUIRED'
  | 'AUTHENTICATION_FAILED'
  | 'RATE_LIMITED'
  | 'TEMPORARILY_UNAVAILABLE'
  | 'REQUIRES_REVIEW'
  | 'PLANNED'
  | 'DISABLED'
  | 'ERROR';

export interface SourceStatusItem {
  source_id: string;
  name: string;
  category: string;
  source_type: string;
  collector_implemented: boolean;
  requires_api_key: boolean;
  status: SourceStatus;
  detail: string;
  priority: number;
  commercial_use_status: string;
  provider: string | null;
  authentication_type: string;
  credential_env_vars: string[];
  capabilities: string[];
  supports_india: boolean;
  reliability_tier: string | null;
  documentation_url: string | null;
  terms_url: string | null;
  connection_status: string | null;
  last_checked_at: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  last_error: string | null;
}

export interface SourceStatusList {
  items: SourceStatusItem[];
  total: number;
  connected_count: number;
  configured_count: number;
  any_connected: boolean;
  data_mode: string;
}

/** Real-data source connectivity registry (GET /sources). */
export async function fetchSources(): Promise<SourceStatusList> {
  const { data } = await api.get<SourceStatusList>('/sources');
  return data;
}

/** Display label + honest Tailwind badge classes for each source status. */
export interface SourceStatusDisplay {
  label: string;
  className: string;
}

const STATUS_DISPLAY: Record<SourceStatus, SourceStatusDisplay> = {
  CONNECTED: {
    label: 'Connected',
    className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
  },
  CONFIGURED: {
    label: 'Configured',
    className: 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300',
  },
  NOT_CONFIGURED: {
    label: 'Not configured',
    className: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
  },
  AUTHENTICATION_REQUIRED: {
    label: 'Authentication required',
    className: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
  },
  AUTHENTICATION_FAILED: {
    label: 'Authentication failed',
    className: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300',
  },
  RATE_LIMITED: {
    label: 'Rate limited',
    className: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
  },
  TEMPORARILY_UNAVAILABLE: {
    label: 'Temporarily unavailable',
    className: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
  },
  REQUIRES_REVIEW: {
    label: 'Requires review',
    className: 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300',
  },
  PLANNED: {
    label: 'Planned',
    className: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  },
  DISABLED: {
    label: 'Disabled',
    className: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  },
  ERROR: {
    label: 'Error',
    className: 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300',
  },
};

export function sourceStatusDisplay(status: SourceStatus): SourceStatusDisplay {
  return (
    STATUS_DISPLAY[status] ?? {
      label: status,
      className: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
    }
  );
}

const EMERALD = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
const BLUE = 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300';
const AMBER = 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300';
const ROSE = 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300';
const SLATE = 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';

const CONNECTION_STATUS_DISPLAY: Record<string, SourceStatusDisplay> = {
  CONNECTED: { label: 'Connected', className: EMERALD },
  CONFIGURED: { label: 'Configured', className: BLUE },
  NOT_CONFIGURED: { label: 'Not configured', className: AMBER },
  AUTHENTICATION_REQUIRED: { label: 'Authentication required', className: AMBER },
  AUTHENTICATION_FAILED: { label: 'Authentication failed', className: ROSE },
  RATE_LIMITED: { label: 'Rate limited', className: AMBER },
  TEMPORARILY_UNAVAILABLE: { label: 'Temporarily unavailable', className: AMBER },
  ERROR: { label: 'Error', className: ROSE },
  DISABLED: { label: 'Disabled', className: SLATE },
  PLANNED: { label: 'Planned', className: SLATE },
};

/** Display label + honest Tailwind badge classes for a live connection_status. */
export function connectionStatusDisplay(status: string): SourceStatusDisplay {
  return (
    CONNECTION_STATUS_DISPLAY[status] ?? {
      label: status,
      className: SLATE,
    }
  );
}
