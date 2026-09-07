import { cn } from '@/utils/cn';
import { alertSeverityDisplay, alertStatusDisplay } from '@/services/alerts';
import { jobStatusDisplay, runStatusDisplay } from '@/services/scheduler';
import type { AlertSeverity, AlertStatus } from '@/services/alerts';
import type { JobStatus, RunStatus } from '@/services/scheduler';

/** Alert severity — colour + label (never colour alone) for accessibility. */
export function SeverityBadge({ severity }: { severity: AlertSeverity }) {
  const { label, className } = alertSeverityDisplay(severity);
  return <span className={cn('badge', className)}>{label}</span>;
}

/** Alert workflow status. */
export function AlertStatusBadge({ status }: { status: AlertStatus }) {
  const { label, className } = alertStatusDisplay(status);
  return <span className={cn('badge', className)}>{label}</span>;
}

/** Scheduled-job status. */
export function JobStatusBadge({ status }: { status: JobStatus }) {
  const { label, className } = jobStatusDisplay(status);
  return <span className={cn('badge', className)}>{label}</span>;
}

/** Scheduler run status. */
export function RunStatusBadge({ status }: { status: RunStatus }) {
  const { label, className } = runStatusDisplay(status);
  return <span className={cn('badge', className)}>{label}</span>;
}
