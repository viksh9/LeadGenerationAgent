import { useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Download, RefreshCw } from 'lucide-react';
import { priorityColor } from '@/utils/format';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { KpiStats } from '@/components/analytics/KpiStats';
import { AnalyticsFilters } from '@/components/analytics/AnalyticsFilters';
import { DistributionCard } from '@/components/analytics/DistributionCard';
import { BarDistribution, DonutDistribution, LineTrend } from '@/components/analytics/charts';
import { IndustryAnalysis } from '@/components/analytics/IndustryAnalysis';
import { TechnologyDemand } from '@/components/analytics/TechnologyDemand';
import { OutreachReadiness } from '@/components/analytics/OutreachReadiness';
import { SourcePerformance } from '@/components/analytics/SourcePerformance';
import { RecentSignals } from '@/components/analytics/RecentSignals';
import { TopOpportunities } from '@/components/analytics/TopOpportunities';
import { useAnalytics } from '@/hooks/useAnalytics';
import { buildAnalytics, filterAnalyticsLeads, rowsToCsv } from '@/services/analytics';
import type { AnalyticsFilters as Filters, DateRange } from '@/types/analytics';

function parseFilters(sp: URLSearchParams): Filters {
  const g = (k: string) => sp.get(k) ?? '';
  return {
    range: (sp.get('range') as DateRange) || 'all',
    industry: g('industry'),
    priority: g('priority') as Filters['priority'],
    signalType: g('signalType') as Filters['signalType'],
    opportunityType: g('opportunityType') as Filters['opportunityType'],
  };
}

function downloadCsv(filename: string, csv: string) {
  if (typeof URL.createObjectURL !== 'function') return;
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function Skeleton() {
  return (
    <div className="space-y-4" aria-hidden="true" data-testid="analytics-skeleton">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-20 animate-pulse rounded-xl bg-slate-100" />
        ))}
      </div>
      <div className="h-16 animate-pulse rounded-xl bg-slate-100" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-64 animate-pulse rounded-xl bg-slate-100" />
        ))}
      </div>
    </div>
  );
}

export function AnalyticsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => parseFilters(searchParams), [searchParams]);

  const { leads, isLoading, isError, isFetching, refetch, isEmpty, datasetLimited, serverTotal, fetchedCount } =
    useAnalytics();

  const now = Date.now();
  const data = useMemo(
    () => buildAnalytics(filterAnalyticsLeads(leads, filters, now), now),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [leads, searchParams],
  );

  const updateParams = (patch: Partial<Filters>) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(patch)) {
          if (value === undefined || value === '' || value === null || value === 'all') next.delete(key);
          else next.set(key, String(value));
        }
        return next;
      },
      { replace: true },
    );
  };

  const handleExport = () => {
    const csv = rowsToCsv(
      ['Industry', 'Leads', 'Hot', 'Avg score', 'High staffing', 'Top opportunity'],
      data.industries.map((r) => [
        r.industry,
        r.leads,
        r.hotLeads,
        r.averageScore,
        r.highStaffing,
        r.topOpportunityLabel ?? '',
      ]),
    );
    downloadCsv('analytics-industries.csv', csv);
  };

  const actions = (
    <div className="flex items-center gap-2">
      <button
        type="button"
        className="btn-secondary text-sm"
        onClick={() => refetch()}
        disabled={isFetching}
        aria-label="Refresh analytics"
      >
        <RefreshCw className={isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
        Refresh
      </button>
      <button
        type="button"
        className="btn-secondary text-sm"
        onClick={handleExport}
        disabled={data.industries.length === 0}
        aria-label="Export analytics as CSV"
      >
        <Download className="h-4 w-4" aria-hidden="true" />
        Export CSV
      </button>
    </div>
  );

  const header = (children: React.ReactNode) => (
    <PageContainer
      title="Analytics"
      subtitle="Understand lead quality, opportunity trends, and business-development performance."
      actions={actions}
    >
      {children}
    </PageContainer>
  );

  if (isLoading) return header(<Skeleton />);
  if (isError)
    return header(
      <Card>
        <ErrorState message="Unable to load analytics." onRetry={() => refetch()} />
      </Card>,
    );
  if (isEmpty || leads.length === 0)
    return header(
      <Card>
        <EmptyState
          title="No analytics available yet."
          description="Analyze more leads to generate meaningful intelligence."
          action={
            <Link to="/leads" className="btn-secondary">
              View leads
            </Link>
          }
        />
      </Card>,
    );

  return header(
    <div className="space-y-4">
      <KpiStats stats={data.stats} />

      <AnalyticsFilters
        filters={filters}
        onChange={updateParams}
        onClear={() => setSearchParams(new URLSearchParams(), { replace: true })}
      />

      <p className="text-xs text-slate-400">
        Based on available lead data{datasetLimited ? ` — top ${fetchedCount} of ${serverTotal?.toLocaleString()} leads` : ''}.
        Status counts are the current distribution, not historical conversion.
      </p>

      {data.totalConsidered === 0 ? (
        <Card>
          <EmptyState
            title="No leads match your filters"
            description="Try a different date range or filter."
            action={
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setSearchParams(new URLSearchParams(), { replace: true })}
              >
                Clear filters
              </button>
            }
          />
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <DistributionCard title="Lead priority distribution">
              <DonutDistribution
                data={data.priority}
                colorFor={(k) => priorityColor[k as keyof typeof priorityColor] ?? '#64748b'}
                ariaLabel="Lead priority distribution"
              />
            </DistributionCard>
            <DistributionCard title="Business signal distribution">
              <BarDistribution data={data.signals} ariaLabel="Business signal distribution" />
            </DistributionCard>
            <DistributionCard title="Opportunity distribution">
              <BarDistribution data={data.opportunities} ariaLabel="Opportunity distribution" />
            </DistributionCard>
            <DistributionCard title="Lead status distribution">
              <BarDistribution data={data.status} ariaLabel="Lead status distribution" />
            </DistributionCard>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <DistributionCard title="Average lead score over time">
              <LineTrend data={data.scoreTrend} dataKey="averageScore" ariaLabel="Average lead score over time" />
            </DistributionCard>
            <DistributionCard title="New leads over time">
              <LineTrend data={data.volumeTrend} dataKey="count" ariaLabel="New leads over time" />
            </DistributionCard>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <IndustryAnalysis industries={data.industries} />
            <TechnologyDemand technologies={data.technologies} />
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            <OutreachReadiness readiness={data.readiness} />
            <TopOpportunities rows={data.topOpportunities} />
            <RecentSignals signals={data.recentSignals} />
          </div>

          <SourcePerformance sources={data.sources} />
        </>
      )}
    </div>,
  );
}
