import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchJobRuns,
  fetchJobs,
  fetchMonitoringDashboard,
  fetchRecentRuns,
  pauseJob,
  resumeJob,
  runJob,
} from '@/services/scheduler';
import { useToast } from '@/contexts/ToastContext';
import { alertKeys } from '@/hooks/useAlerts';
import type { ApiErrorShape } from '@/services/api';

const errText = (e: unknown, fallback: string) =>
  (e as ApiErrorShape | undefined)?.message ?? fallback;

/** Centralized query keys for the scheduler / monitoring layer. */
export const schedulerKeys = {
  all: ['scheduler'] as const,
  jobs: () => [...schedulerKeys.all, 'jobs'] as const,
  jobRuns: (id: number, limit?: number) =>
    [...schedulerKeys.all, 'jobs', id, 'runs', limit ?? 'all'] as const,
  runs: (limit?: number) => [...schedulerKeys.all, 'runs', limit ?? 'all'] as const,
  dashboard: ['monitoring', 'dashboard'] as const,
};

export function useJobs() {
  return useQuery({
    queryKey: schedulerKeys.jobs(),
    queryFn: ({ signal }) => fetchJobs(signal),
  });
}

export function useJobRuns(id: number, limit?: number) {
  return useQuery({
    queryKey: schedulerKeys.jobRuns(id, limit),
    queryFn: ({ signal }) => fetchJobRuns(id, limit, signal),
    enabled: Number.isFinite(id),
  });
}

export function useRecentRuns(limit?: number) {
  return useQuery({
    queryKey: schedulerKeys.runs(limit),
    queryFn: ({ signal }) => fetchRecentRuns(limit, signal),
  });
}

export function useMonitoringDashboard() {
  return useQuery({
    queryKey: schedulerKeys.dashboard,
    queryFn: ({ signal }) => fetchMonitoringDashboard(signal),
  });
}

// A run can change pipeline counts and raise alerts, so refresh the scheduler
// views, the monitoring dashboard, and the alert queries after each action.
function useJobActionInvalidate() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: schedulerKeys.all });
    qc.invalidateQueries({ queryKey: schedulerKeys.dashboard });
    qc.invalidateQueries({ queryKey: alertKeys.all });
  };
}

export function useRunJob() {
  const invalidate = useJobActionInvalidate();
  const toast = useToast();
  return useMutation({
    mutationFn: (id: number) => runJob(id),
    onSuccess: () => {
      invalidate();
      toast.success('Job run triggered.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to run this job.')),
  });
}

export function usePauseJob() {
  const invalidate = useJobActionInvalidate();
  const toast = useToast();
  return useMutation({
    mutationFn: (id: number) => pauseJob(id),
    onSuccess: () => {
      invalidate();
      toast.success('Job paused.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to pause this job.')),
  });
}

export function useResumeJob() {
  const invalidate = useJobActionInvalidate();
  const toast = useToast();
  return useMutation({
    mutationFn: (id: number) => resumeJob(id),
    onSuccess: () => {
      invalidate();
      toast.success('Job resumed.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to resume this job.')),
  });
}
