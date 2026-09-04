import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Flame, Target, ThermometerSun, Trophy } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { DashboardKpiCard } from '@/components/dashboard/DashboardKpiCard';
import { DashboardSkeleton } from '@/components/dashboard/DashboardSkeleton';
import { PriorityDistributionChart } from '@/components/dashboard/PriorityDistributionChart';
import { QuickActions } from '@/components/dashboard/QuickActions';
import { RecentActivity } from '@/components/dashboard/RecentActivity';
import { RecentSignals } from '@/components/dashboard/RecentSignals';
import { SignalDistributionChart } from '@/components/dashboard/SignalDistributionChart';
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
    <div className="inline-flex rounded-md border border-slate-300 bg-white p-0.5" role="group" aria-label="Date range">
      {RANGE_OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={
            value === option.value
              ? 'rounded px-3 py-1.5 text-sm font-medium bg-brand-600 text-white'
              : 'rounded px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100'
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
  const { data, isLoading, isError, refetch, isEmpty } = useDashboard(range);

  const subtitle = 'Identify and prioritize the most valuable business opportunities.';

  let body;
  if (isLoading) {
    body = <DashboardSkeleton />;
  } else if (isError) {
    body = <ErrorState message="Unable to load lead intelligence." onRetry={() => refetch()} />;
  } else if (isEmpty || !data) {
    body = (
      <EmptyState
        title="No leads available yet."
        description="Analyze your first lead to start building your lead intelligence."
        action={
          <Link to="/leads/analyze" className="btn-primary">
            Analyze New Lead
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

        <section className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <SignalDistributionChart data={data.signalDistribution} />
          <PriorityDistributionChart data={data.priorityDistribution} />
        </section>

        <section className="mt-6">
          <TopOpportunitiesTable leads={data.topOpportunities} />
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
      </>
    );
  }

  return (
    <PageContainer
      title="Lead Intelligence Dashboard"
      subtitle={subtitle}
      actions={!isLoading && !isError ? <RangeFilter value={range} onChange={setRange} /> : undefined}
    >
      {body}
    </PageContainer>
  );
}
