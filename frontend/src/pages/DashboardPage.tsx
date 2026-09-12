import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Flame, Target, ThermometerSun, Trophy } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { DataProvenanceBanner } from '@/components/common/DataProvenanceBanner';
import { DashboardKpiCard } from '@/components/dashboard/DashboardKpiCard';
import { ExportAllData } from '@/components/dashboard/ExportAllData';
import { DashboardSkeleton } from '@/components/dashboard/DashboardSkeleton';
import { PriorityDistributionChart } from '@/components/dashboard/PriorityDistributionChart';
import { QuickActions } from '@/components/dashboard/QuickActions';
import { RecentActivity } from '@/components/dashboard/RecentActivity';
import { RecentSignals } from '@/components/dashboard/RecentSignals';
import { SalesQueue } from '@/components/dashboard/SalesQueue';
import { SignalDistributionChart } from '@/components/dashboard/SignalDistributionChart';
import { SourceCoverage } from '@/components/dashboard/SourceCoverage';
import { TopOpportunitiesTable } from '@/components/dashboard/TopOpportunitiesTable';
import { useDashboard } from '@/hooks/useDashboard';
import type { DateRange } from '@/types/dashboard';

const RANGE_OPTIONS: { value: DateRange; label: string }[] = [
  { value: 'all', label: 'All Time' },
  { value: '7d', label: 'Last 7 Days' },
  { value: '30d', label: 'Last 30 Days' },
];

function RangeFilter({ value, onChange }: { value: DateRange; onChange: (v: DateRange) => void }) {
  return (
    <div className="inline-flex rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 p-0.5" role="group" aria-label="Date range">
      {RANGE_OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={
            value === option.value
              ? 'rounded px-3 py-1.5 text-sm font-medium bg-brand-600 text-white'
              : 'rounded px-3 py-1.5 text-sm font-medium text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
          }
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function DashboardPage() {
  const [range, setRange] = useState<DateRange>('all');
  const { data, provenance, trust, isLoading, isError, refetch, isEmpty } = useDashboard(range);

  const subtitle = 'Company-level Indian IT hiring opportunities from real collected signals.';

  let body;
  if (isLoading) {
    body = <DashboardSkeleton />;
  } else if (isError) {
    body = <ErrorState message="Unable to load lead intelligence." onRetry={() => refetch()} />;
  } else if (isEmpty || !data) {
    body = (
      <EmptyState
        title="No verified Indian IT signals available yet."
        description="No real data source is connected yet. Configure and verify a collector, then aggregate company-level opportunities from real collected jobs."
        action={
          <Link to="/leads/analyze" className="btn-primary">
            Analyze a Company
          </Link>
        }
      />
    );
  } else {
    const { stats } = data;
    const datasetNote = stats.datasetLimited
      ? `From the top ${stats.fetchedCount} of ${stats.serverTotal.toLocaleString()} leads`
      : undefined;
    body = (
      <>
        {provenance.demoOnly && <DataProvenanceBanner />}
        <section
          aria-label="Key metrics"
          className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4"
        >
          <DashboardKpiCard
            title="Total Leads"
            value={range === 'all' ? stats.serverTotal : stats.totalInDataset}
            description="All active leads"
            icon={Target}
            note={range === 'all' ? undefined : 'In selected range (dataset)'}
          />
          <DashboardKpiCard
            title="Hot Leads"
            value={stats.priorityCounts.HOT}
            description="Immediate attention"
            icon={Flame}
            accent="text-rose-600"
            note={datasetNote}
          />
          <DashboardKpiCard
            title="Warm Leads"
            value={stats.priorityCounts.WARM}
            description="Requires qualification"
            icon={ThermometerSun}
            accent="text-amber-600"
            note={datasetNote}
          />
          <DashboardKpiCard
            title="Qualified Opportunities"
            value={stats.qualifiedCount}
            description="Potential sales opportunities"
            icon={Trophy}
            accent="text-emerald-600"
            note={datasetNote}
          />
        </section>

        <section className="mt-6 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
              Data trust — verified vs unverified intelligence
            </h2>
            <span className="text-xs text-slate-400 dark:text-slate-500">
              {trust.ready} production-ready of {trust.total}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {([
              ['Verified', trust.counts.VERIFIED, 'text-emerald-600'],
              ['Partial', trust.counts.PARTIALLY_VERIFIED, 'text-amber-600'],
              ['Unverified', trust.counts.UNVERIFIED, 'text-slate-500'],
              ['Stale', trust.counts.STALE, 'text-zinc-500'],
              ['Contradicted', trust.counts.CONTRADICTED, 'text-rose-600'],
            ] as const).map(([label, count, color]) => (
              <div key={label} className="rounded-md bg-slate-50 dark:bg-slate-800/60 p-3 text-center">
                <p className={`text-xl font-semibold ${color}`}>{count}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
            Verification is independent of the commercial lead score.
          </p>
        </section>

        <section className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <SignalDistributionChart data={data.signalDistribution} />
          <PriorityDistributionChart data={data.priorityDistribution} />
        </section>

        <section className="mt-6">
          <TopOpportunitiesTable leads={data.topOpportunities} />
        </section>

        <section className="mt-6">
          <SalesQueue />
        </section>

        <section className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-1">
            <RecentSignals leads={data.recentSignals} />
          </div>
          <div className="lg:col-span-1">
            <RecentActivity items={data.recentActivity} />
          </div>
          <div className="lg:col-span-1">
            <QuickActions />
          </div>
        </section>

        <section className="mt-6">
          <SourceCoverage />
        </section>
      </>
    );
  }

  return (
    <PageContainer
      title="Lead Intelligence Dashboard"
      subtitle={subtitle}
      actions={
        <>
          {!isLoading && !isError ? <RangeFilter value={range} onChange={setRange} /> : null}
          <ExportAllData />
        </>
      }
    >
      {body}
    </PageContainer>
  );
}
