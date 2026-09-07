import { Link } from 'react-router-dom';
import {
  Boxes,
  Briefcase,
  Building2,
  FileText,
  Pause,
  Play,
  RadioTower,
  RefreshCw,
  Sparkles,
  Target,
} from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { DashboardKpiCard } from '@/components/dashboard/DashboardKpiCard';
import { DetailCard } from '@/components/leads/detail/DetailCard';
import { Table, Td, Th } from '@/components/ui/Table';
import { ErrorState, LoadingState } from '@/components/ui/States';
import {
  AlertStatusBadge,
  JobStatusBadge,
  RunStatusBadge,
  SeverityBadge,
} from '@/components/alerts/badges';
import { connectionStatusDisplay } from '@/services/sources';
import { alertTypeLabel } from '@/services/alerts';
import { formatInterval } from '@/services/scheduler';
import {
  useJobs,
  useMonitoringDashboard,
  usePauseJob,
  useResumeJob,
  useRunJob,
} from '@/hooks/useScheduler';
import { formatDateTime, formatDuration, relativeTime } from '@/utils/format';
import type { ScheduledJob } from '@/services/scheduler';

function SchedulerBanner({ enabled }: { enabled: boolean }) {
  if (enabled) {
    return (
      <div className="mb-6 flex items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300">
        <RefreshCw className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <p>
          The background scheduler is <strong>enabled</strong>. Jobs run automatically on their
          configured cadence.
        </p>
      </div>
    );
  }
  return (
    <div className="mb-6 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
      <Pause className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <p>
        The background scheduler is <strong>disabled</strong>. Jobs do not run automatically — they
        can be triggered manually below or via the CLI.
      </p>
    </div>
  );
}

function JobActions({ job }: { job: ScheduledJob }) {
  const runJob = useRunJob();
  const pauseJob = usePauseJob();
  const resumeJob = useResumeJob();
  const busy = runJob.isPending || pauseJob.isPending || resumeJob.isPending;

  return (
    <div className="flex items-center gap-1.5">
      <button
        type="button"
        className="btn-ghost text-xs"
        disabled={busy}
        onClick={() => runJob.mutate(job.id)}
      >
        <Play className="h-3.5 w-3.5" aria-hidden="true" />
        Run
      </button>
      {job.current_status === 'PAUSED' ? (
        <button
          type="button"
          className="btn-ghost text-xs"
          disabled={busy}
          onClick={() => resumeJob.mutate(job.id)}
        >
          <Play className="h-3.5 w-3.5" aria-hidden="true" />
          Resume
        </button>
      ) : (
        <button
          type="button"
          className="btn-ghost text-xs"
          disabled={busy}
          onClick={() => pauseJob.mutate(job.id)}
        >
          <Pause className="h-3.5 w-3.5" aria-hidden="true" />
          Pause
        </button>
      )}
    </div>
  );
}

export function MonitoringPage() {
  // The dashboard endpoint carries jobs, but a dedicated jobs query keeps the
  // Run/Pause/Resume actions reactive after mutations.
  const dashboard = useMonitoringDashboard();
  const jobsQuery = useJobs();

  let body;
  if (dashboard.isLoading) {
    body = <LoadingState message="Loading monitoring dashboard…" />;
  } else if (dashboard.isError || !dashboard.data) {
    body = (
      <ErrorState
        message="Unable to load the monitoring dashboard."
        onRetry={() => dashboard.refetch()}
      />
    );
  } else {
    const data = dashboard.data;
    const { pipeline } = data;
    const jobs = jobsQuery.data?.items ?? data.jobs;

    const pipelineCards: { title: string; value: number; description: string; icon: typeof Boxes }[] = [
      { title: 'Raw records', value: pipeline.raw_records, description: 'Collected source rows', icon: Boxes },
      { title: 'Canonical jobs', value: pipeline.canonical_jobs, description: 'Deduplicated postings', icon: Briefcase },
      { title: 'Companies', value: pipeline.companies, description: 'Resolved entities', icon: Building2 },
      { title: 'Signals', value: pipeline.signals, description: 'Buying signals', icon: RadioTower },
      { title: 'Opportunities', value: pipeline.opportunities, description: 'Derived opportunities', icon: Sparkles },
      { title: 'Leads', value: pipeline.leads, description: 'Qualified leads', icon: Target },
      { title: 'Tenders', value: pipeline.tenders, description: 'Tracked tenders', icon: FileText },
    ];

    body = (
      <>
        <SchedulerBanner enabled={data.scheduler_enabled} />

        <section aria-label="Pipeline metrics" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {pipelineCards.map((card) => (
            <DashboardKpiCard
              key={card.title}
              title={card.title}
              value={card.value}
              description={card.description}
              icon={card.icon}
            />
          ))}
        </section>

        <section className="mt-6">
          <DetailCard title="Data sources">
            {data.sources.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">No data sources registered.</p>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Source</Th>
                    <Th>Connectivity</Th>
                    <Th>Last success</Th>
                    <Th>Last failure</Th>
                    <Th>Last run</Th>
                    <Th>Records fetched</Th>
                    <Th>Last error</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.sources.map((source) => {
                    const conn = connectionStatusDisplay(source.connection_status);
                    return (
                      <tr key={source.source_id}>
                        <Td>
                          <span className="font-medium text-slate-800 dark:text-slate-200">
                            {source.source_id}
                          </span>
                        </Td>
                        <Td>
                          <span className={`badge ${conn.className}`}>{conn.label}</span>
                        </Td>
                        <Td>{formatDateTime(source.last_success_at)}</Td>
                        <Td>{formatDateTime(source.last_failure_at)}</Td>
                        <Td>{source.last_run_at ? relativeTime(source.last_run_at) : '—'}</Td>
                        <Td>
                          <span className="tabular-nums">{source.records_fetched.toLocaleString()}</span>
                        </Td>
                        <Td>
                          {source.last_error ? (
                            <span className="text-rose-600 dark:text-rose-400">{source.last_error}</span>
                          ) : (
                            '—'
                          )}
                        </Td>
                      </tr>
                    );
                  })}
                </tbody>
              </Table>
            )}
          </DetailCard>
        </section>

        <section className="mt-6">
          <DetailCard title="Scheduled jobs">
            {jobs.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">No scheduled jobs configured.</p>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Job</Th>
                    <Th>Type</Th>
                    <Th>Status</Th>
                    <Th>Enabled</Th>
                    <Th>Cadence</Th>
                    <Th>Next run</Th>
                    <Th>Last error</Th>
                    <Th>Actions</Th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id}>
                      <Td>
                        <span className="font-medium text-slate-800 dark:text-slate-200">
                          {job.job_name}
                        </span>
                      </Td>
                      <Td>{job.job_type}</Td>
                      <Td>
                        <JobStatusBadge status={job.current_status} />
                      </Td>
                      <Td>{job.enabled ? 'Yes' : 'No'}</Td>
                      <Td>{job.schedule ?? formatInterval(job.interval_seconds)}</Td>
                      <Td>{job.next_run_at ? relativeTime(job.next_run_at) : '—'}</Td>
                      <Td>
                        {job.last_error ? (
                          <span className="text-rose-600 dark:text-rose-400">{job.last_error}</span>
                        ) : (
                          '—'
                        )}
                      </Td>
                      <Td>
                        <JobActions job={job} />
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </DetailCard>
        </section>

        <section className="mt-6">
          <DetailCard title="Recent runs">
            {data.recent_runs.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">No runs yet.</p>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Job</Th>
                    <Th>Status</Th>
                    <Th>Started</Th>
                    <Th>Duration</Th>
                    <Th>Fetched</Th>
                    <Th>New</Th>
                    <Th>Changed</Th>
                    <Th>Alerts</Th>
                    <Th>Error</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_runs.map((run) => (
                    <tr key={run.id}>
                      <Td>
                        <span className="font-medium text-slate-800 dark:text-slate-200">
                          {run.job_name}
                        </span>
                      </Td>
                      <Td>
                        <RunStatusBadge status={run.status} />
                      </Td>
                      <Td>{relativeTime(run.started_at)}</Td>
                      <Td>{formatDuration(run.duration_seconds)}</Td>
                      <Td>
                        <span className="tabular-nums">{run.records_fetched.toLocaleString()}</span>
                      </Td>
                      <Td>
                        <span className="tabular-nums">{run.records_new.toLocaleString()}</span>
                      </Td>
                      <Td>
                        <span className="tabular-nums">{run.records_changed.toLocaleString()}</span>
                      </Td>
                      <Td>
                        <span className="tabular-nums">{run.alerts_generated.toLocaleString()}</span>
                      </Td>
                      <Td>
                        {run.error ? (
                          <span className="text-rose-600 dark:text-rose-400">{run.error}</span>
                        ) : (
                          '—'
                        )}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </DetailCard>
        </section>

        <section className="mt-6">
          <DetailCard title="Recent high-value changes">
            {data.recent_alerts.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">No alerts yet.</p>
            ) : (
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {data.recent_alerts.map((alert) => (
                  <li key={alert.id} className="py-3 first:pt-0 last:pb-0">
                    <Link
                      to={alert.link ?? '/monitoring'}
                      className="block rounded focus:outline-none focus:ring-2 focus:ring-brand-500"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <SeverityBadge severity={alert.severity} />
                        <AlertStatusBadge status={alert.status} />
                        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                          {alertTypeLabel(alert.alert_type)}
                        </span>
                        <span className="ml-auto text-xs text-slate-400 dark:text-slate-500">
                          {relativeTime(alert.triggered_at)}
                        </span>
                      </div>
                      <p className="mt-1 text-sm font-medium text-slate-900 dark:text-slate-100">
                        {alert.title}
                      </p>
                      {alert.message && (
                        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{alert.message}</p>
                      )}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </DetailCard>
        </section>

        <p className="mt-6 text-xs text-slate-400 dark:text-slate-500">
          Data mode: {data.data_mode} · Snapshot generated {formatDateTime(data.generated_at)}
        </p>
      </>
    );
  }

  return (
    <PageContainer
      title="Monitoring"
      subtitle="Continuous ingestion pipeline health, scheduled jobs, and recent high-value changes."
      actions={
        <button
          type="button"
          className="btn-secondary text-sm"
          onClick={() => dashboard.refetch()}
          disabled={dashboard.isFetching}
        >
          <RefreshCw
            className={dashboard.isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
            aria-hidden="true"
          />
          Refresh
        </button>
      }
    >
      {body}
    </PageContainer>
  );
}
