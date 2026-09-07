import { screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/test-utils';
import { MonitoringPage } from './MonitoringPage';
import type { MonitoringDashboard, ScheduledJobList } from '@/services/scheduler';

// Keep the real display helpers; stub only the network fetchers.
vi.mock('@/services/scheduler', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/scheduler')>();
  return {
    ...actual,
    fetchMonitoringDashboard: vi.fn(),
    fetchJobs: vi.fn(),
  };
});
import { fetchJobs, fetchMonitoringDashboard } from '@/services/scheduler';
const fetchDashboardMock = vi.mocked(fetchMonitoringDashboard);
const fetchJobsMock = vi.mocked(fetchJobs);

function makeDashboard(p: Partial<MonitoringDashboard> = {}): MonitoringDashboard {
  return {
    generated_at: '2026-09-05T10:00:00Z',
    scheduler_enabled: true,
    data_mode: 'REAL_ONLY',
    pipeline: {
      raw_records: 1200,
      canonical_jobs: 340,
      companies: 87,
      signals: 51,
      opportunities: 33,
      leads: 24,
      tenders: 6,
    },
    sources: [
      {
        source_id: 'adzuna',
        connection_status: 'CONNECTED',
        last_success_at: '2026-09-05T09:30:00Z',
        last_failure_at: null,
        last_error: null,
        last_run_at: '2026-09-05T09:30:00Z',
        records_fetched: 120,
      },
    ],
    jobs: [
      {
        id: 1,
        job_name: 'Adzuna ingestion',
        job_type: 'INGEST',
        enabled: true,
        interval_seconds: 3600,
        schedule: null,
        timezone: 'UTC',
        source_id: 'adzuna',
        current_status: 'SCHEDULED',
        consecutive_failures: 0,
        max_retries: 3,
        last_run_at: '2026-09-05T09:30:00Z',
        last_success_at: '2026-09-05T09:30:00Z',
        last_failure_at: null,
        next_run_at: '2026-09-05T10:30:00Z',
        last_error: null,
      },
    ],
    recent_runs: [
      {
        id: 10,
        job_name: 'Adzuna ingestion',
        job_type: 'INGEST',
        source_id: 'adzuna',
        trigger: 'SCHEDULE',
        status: 'SUCCESS',
        started_at: '2026-09-05T09:30:00Z',
        finished_at: '2026-09-05T09:31:00Z',
        duration_seconds: 60,
        retry_count: 0,
        records_fetched: 120,
        records_new: 12,
        records_changed: 3,
        records_unchanged: 105,
        records_removed: 0,
        signals_changed: 4,
        opportunities_changed: 2,
        leads_changed: 1,
        alerts_generated: 2,
        error: null,
      },
    ],
    recent_alerts: [
      {
        id: 100,
        alert_type: 'NEW_HIGH_INTENT_LEAD',
        severity: 'HIGH',
        status: 'NEW',
        title: 'NorthStar Banking flagged as high intent',
        message: 'Score increased after a project award.',
        company_id: 42,
        lead_id: 7,
        opportunity_id: null,
        signal_id: null,
        tender_id: null,
        source_id: null,
        evidence_ids: [1],
        link: '/leads/7',
        triggered_at: '2026-09-05T09:31:00Z',
        acknowledged_at: null,
        resolved_at: null,
      },
    ],
    unread_alerts: 1,
    job_change_summary: [{ change_type: 'NEW_LEAD', count: 1 }],
    ...p,
  };
}

function makeJobList(dashboard: MonitoringDashboard): ScheduledJobList {
  return { items: dashboard.jobs, total: dashboard.jobs.length, scheduler_enabled: dashboard.scheduler_enabled };
}

beforeEach(() => {
  fetchDashboardMock.mockReset();
  fetchJobsMock.mockReset();
});
afterEach(() => vi.clearAllMocks());

describe('MonitoringPage', () => {
  it('renders pipeline KPIs, a source row, a job row and a run', async () => {
    const dashboard = makeDashboard();
    fetchDashboardMock.mockResolvedValue(dashboard);
    fetchJobsMock.mockResolvedValue(makeJobList(dashboard));

    renderWithProviders(<MonitoringPage />, { route: '/monitoring' });

    // Pipeline KPI titles + values.
    expect(await screen.findByText('Companies')).toBeInTheDocument();
    expect(screen.getByText('Raw records')).toBeInTheDocument();
    expect(screen.getByText('1,200')).toBeInTheDocument(); // raw_records, localized
    expect(screen.getByText('87')).toBeInTheDocument(); // companies

    // Source row.
    expect(screen.getByText('adzuna')).toBeInTheDocument();

    // Job row.
    expect(screen.getAllByText('Adzuna ingestion').length).toBeGreaterThan(0);
    expect(screen.getByText('Every 1h')).toBeInTheDocument();

    // Recent alert links through.
    expect(screen.getByText('NorthStar Banking flagged as high intent')).toBeInTheDocument();
  });

  it('shows the disabled banner when the scheduler is off', async () => {
    const dashboard = makeDashboard({ scheduler_enabled: false });
    fetchDashboardMock.mockResolvedValue(dashboard);
    fetchJobsMock.mockResolvedValue(makeJobList(dashboard));

    renderWithProviders(<MonitoringPage />, { route: '/monitoring' });

    expect(await screen.findByText(/background scheduler is/i)).toBeInTheDocument();
    expect(screen.getByText(/triggered manually/i)).toBeInTheDocument();
  });

  it('shows an error state when the dashboard fails to load', async () => {
    fetchDashboardMock.mockRejectedValue({ code: 'error', message: 'boom' });
    fetchJobsMock.mockResolvedValue({ items: [], total: 0, scheduler_enabled: false });

    renderWithProviders(<MonitoringPage />, { route: '/monitoring' });

    expect(await screen.findByText(/unable to load the monitoring dashboard/i)).toBeInTheDocument();
  });
});
