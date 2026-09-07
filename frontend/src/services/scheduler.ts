import { api } from './api';
import type { Alert } from './alerts';

/**
 * Thin API client + display helpers for the continuous monitoring & scheduling
 * layer: scheduled ingestion jobs, their run history, and the monitoring
 * dashboard. Every number reported here comes straight from the backend — the
 * UI never fabricates pipeline counts.
 */

export type JobStatus =
  | 'DISABLED'
  | 'SCHEDULED'
  | 'RUNNING'
  | 'SUCCESS'
  | 'FAILED'
  | 'PAUSED';

export type RunStatus = 'RUNNING' | 'SUCCESS' | 'FAILED' | 'SKIPPED' | 'PARTIAL';

export interface ScheduledJob {
  id: number;
  job_name: string;
  job_type: string;
  enabled: boolean;
  interval_seconds: number;
  schedule?: string | null;
  timezone: string;
  source_id?: string | null;
  current_status: JobStatus;
  consecutive_failures: number;
  max_retries: number;
  last_run_at?: string | null;
  last_success_at?: string | null;
  last_failure_at?: string | null;
  next_run_at?: string | null;
  last_error?: string | null;
}

export interface SchedulerRun {
  id: number;
  job_name: string;
  job_type: string;
  source_id?: string | null;
  trigger: string;
  status: RunStatus;
  started_at: string;
  finished_at?: string | null;
  duration_seconds?: number | null;
  retry_count: number;
  records_fetched: number;
  records_new: number;
  records_changed: number;
  records_unchanged: number;
  records_removed: number;
  signals_changed: number;
  opportunities_changed: number;
  leads_changed: number;
  alerts_generated: number;
  error?: string | null;
}

export interface ScheduledJobList {
  items: ScheduledJob[];
  total: number;
  scheduler_enabled: boolean;
}

export interface SchedulerRunList {
  items: SchedulerRun[];
  total: number;
}

export interface MonitoringPipeline {
  raw_records: number;
  canonical_jobs: number;
  companies: number;
  signals: number;
  opportunities: number;
  leads: number;
  tenders: number;
}

export interface MonitoringSource {
  source_id: string;
  connection_status: string;
  last_success_at?: string | null;
  last_failure_at?: string | null;
  last_error?: string | null;
  last_run_at?: string | null;
  records_fetched: number;
}

export interface JobChangeSummary {
  change_type: string;
  count: number;
}

export interface MonitoringDashboard {
  generated_at: string;
  scheduler_enabled: boolean;
  data_mode: string;
  pipeline: MonitoringPipeline;
  sources: MonitoringSource[];
  jobs: ScheduledJob[];
  recent_runs: SchedulerRun[];
  recent_alerts: Alert[];
  unread_alerts: number;
  job_change_summary: JobChangeSummary[];
}

/** All scheduled jobs and whether the background runner is enabled. */
export async function fetchJobs(signal?: AbortSignal): Promise<ScheduledJobList> {
  const { data } = await api.get<ScheduledJobList>('/scheduler/jobs', { signal });
  return data;
}

/** A single scheduled job (GET /scheduler/jobs/{id}). */
export async function fetchJob(id: number, signal?: AbortSignal): Promise<ScheduledJob> {
  const { data } = await api.get<ScheduledJob>(`/scheduler/jobs/${id}`, { signal });
  return data;
}

/** Run history for a single job (GET /scheduler/jobs/{id}/runs). */
export async function fetchJobRuns(
  id: number,
  limit?: number,
  signal?: AbortSignal,
): Promise<SchedulerRunList> {
  const { data } = await api.get<SchedulerRunList>(`/scheduler/jobs/${id}/runs`, {
    params: limit ? { limit } : undefined,
    signal,
  });
  return data;
}

/** Recent runs across all jobs (GET /scheduler/runs). */
export async function fetchRecentRuns(
  limit?: number,
  signal?: AbortSignal,
): Promise<SchedulerRunList> {
  const { data } = await api.get<SchedulerRunList>('/scheduler/runs', {
    params: limit ? { limit } : undefined,
    signal,
  });
  return data;
}

/** Trigger a job to run now (admin-guarded server-side; no auth header sent). */
export async function runJob(id: number): Promise<SchedulerRun | ScheduledJob> {
  const { data } = await api.post<SchedulerRun | ScheduledJob>(`/scheduler/jobs/${id}/run`);
  return data;
}

/** Pause a scheduled job. */
export async function pauseJob(id: number): Promise<ScheduledJob> {
  const { data } = await api.post<ScheduledJob>(`/scheduler/jobs/${id}/pause`);
  return data;
}

/** Resume a paused job. */
export async function resumeJob(id: number): Promise<ScheduledJob> {
  const { data } = await api.post<ScheduledJob>(`/scheduler/jobs/${id}/resume`);
  return data;
}

/** The monitoring dashboard snapshot (GET /monitoring/dashboard). */
export async function fetchMonitoringDashboard(
  signal?: AbortSignal,
): Promise<MonitoringDashboard> {
  const { data } = await api.get<MonitoringDashboard>('/monitoring/dashboard', { signal });
  return data;
}

export interface SchedulerDisplay {
  label: string;
  className: string;
}

const EMERALD = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
const BLUE = 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300';
const AMBER = 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300';
const ROSE = 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300';
const SLATE = 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';

const JOB_STATUS_DISPLAY: Record<JobStatus, SchedulerDisplay> = {
  SUCCESS: { label: 'Success', className: EMERALD },
  RUNNING: { label: 'Running', className: BLUE },
  SCHEDULED: { label: 'Scheduled', className: BLUE },
  FAILED: { label: 'Failed', className: ROSE },
  PAUSED: { label: 'Paused', className: SLATE },
  DISABLED: { label: 'Disabled', className: SLATE },
};

/** Display label + honest Tailwind badge classes for a scheduled-job status. */
export function jobStatusDisplay(status: JobStatus): SchedulerDisplay {
  return JOB_STATUS_DISPLAY[status] ?? { label: status, className: SLATE };
}

const RUN_STATUS_DISPLAY: Record<RunStatus, SchedulerDisplay> = {
  SUCCESS: { label: 'Success', className: EMERALD },
  RUNNING: { label: 'Running', className: BLUE },
  FAILED: { label: 'Failed', className: ROSE },
  PARTIAL: { label: 'Partial', className: AMBER },
  SKIPPED: { label: 'Skipped', className: SLATE },
};

/** Display label + honest Tailwind badge classes for a run status. */
export function runStatusDisplay(status: RunStatus): SchedulerDisplay {
  return RUN_STATUS_DISPLAY[status] ?? { label: status, className: SLATE };
}

/** Human-readable cadence from an interval in seconds (e.g. "Every 30m"). */
export function formatInterval(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return 'On demand';
  const units: [number, string][] = [
    [86_400, 'd'],
    [3_600, 'h'],
    [60, 'm'],
    [1, 's'],
  ];
  for (const [size, suffix] of units) {
    if (seconds >= size && seconds % size === 0) {
      return `Every ${seconds / size}${suffix}`;
    }
  }
  // Non-round intervals: fall back to the largest sensible unit.
  if (seconds >= 3_600) return `Every ${Math.round(seconds / 3_600)}h`;
  if (seconds >= 60) return `Every ${Math.round(seconds / 60)}m`;
  return `Every ${seconds}s`;
}
