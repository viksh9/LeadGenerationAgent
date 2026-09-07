import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { OpportunitySummary } from '@/components/opportunities/OpportunitySummary';
import { QuickFilterTabs } from '@/components/opportunities/QuickFilterTabs';
import { OpportunityFilters } from '@/components/opportunities/OpportunityFilters';
import { OpportunityTable } from '@/components/opportunities/OpportunityTable';
import { OpportunityCard } from '@/components/opportunities/OpportunityCard';
import { TopOpportunities } from '@/components/opportunities/TopOpportunities';
import { OpportunityChart } from '@/components/opportunities/OpportunityChart';
import { OpportunityDetailDrawer } from '@/components/opportunities/OpportunityDetailDrawer';
import { useDebounce } from '@/hooks/useDebounce';
import { useOpportunities } from '@/hooks/useOpportunities';
import {
  buildOpportunitySummary,
  buildTypeDistribution,
  filterOpportunities,
  sortOpportunities,
} from '@/services/opportunities';
import type {
  Opportunity,
  OpportunityFilterState,
  OpportunitySortBy,
} from '@/types/opportunity';

function parseFilters(sp: URLSearchParams): OpportunityFilterState {
  const g = (k: string) => sp.get(k) ?? '';
  return {
    search: g('search'),
    type: g('type') as OpportunityFilterState['type'],
    priority: g('priority') as OpportunityFilterState['priority'],
    staffing: g('staffing') as OpportunityFilterState['staffing'],
    urgency: g('urgency') as OpportunityFilterState['urgency'],
    industry: g('industry'),
    technology: g('technology'),
    status: g('status') as OpportunityFilterState['status'],
  };
}

function Skeleton() {
  return (
    <div className="space-y-4" aria-hidden="true" data-testid="opportunities-skeleton">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-20 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
        ))}
      </div>
      <div className="h-20 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="h-96 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800 lg:col-span-2" />
        <div className="h-96 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
      </div>
    </div>
  );
}

export function OpportunitiesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => parseFilters(searchParams), [searchParams]);
  const sortBy = (searchParams.get('sort') as OpportunitySortBy) || 'score';

  const [searchText, setSearchText] = useState(filters.search);
  const debouncedSearch = useDebounce(searchText, 350);

  const [selected, setSelected] = useState<Opportunity | null>(null);

  const { opportunities, isLoading, isError, isFetching, refetch, isEmpty, datasetLimited, serverTotal, fetchedCount } =
    useOpportunities();

  const updateParams = (patch: Partial<OpportunityFilterState> & { sort?: OpportunitySortBy }) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(patch)) {
          if (value === undefined || value === '' || value === null) next.delete(key);
          else next.set(key, String(value));
        }
        return next;
      },
      { replace: true },
    );
  };

  useEffect(() => {
    if (debouncedSearch !== (searchParams.get('search') ?? '')) {
      updateParams({ search: debouncedSearch });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  const effectiveFilters: OpportunityFilterState = { ...filters, search: debouncedSearch };

  const base = useMemo(() => opportunities ?? [], [opportunities]);
  const visible = useMemo(
    () => sortOpportunities(filterOpportunities(base, effectiveFilters), sortBy),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [base, searchParams, debouncedSearch, sortBy],
  );
  const summary = useMemo(() => buildOpportunitySummary(base), [base]);
  const distribution = useMemo(() => buildTypeDistribution(base), [base]);

  const hasActiveFilters =
    Boolean(debouncedSearch) ||
    (['type', 'priority', 'staffing', 'urgency', 'industry', 'technology', 'status'] as const).some(
      (k) => filters[k] !== '',
    );

  const handleClear = () => {
    setSearchText('');
    setSearchParams(new URLSearchParams(), { replace: true });
  };

  const actions = (
    <div className="flex items-center gap-2">
      <button
        type="button"
        className="btn-secondary text-sm"
        onClick={() => refetch()}
        disabled={isFetching}
        aria-label="Refresh opportunities"
      >
        <RefreshCw className={isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
        Refresh
      </button>
      <Link to="/leads" className="btn-secondary text-sm">
        View leads
      </Link>
    </div>
  );

  const header = (children: React.ReactNode) => (
    <PageContainer
      title="Opportunities"
      subtitle="Prioritize qualified business opportunities based on demand, urgency, and fit."
      actions={actions}
    >
      {children}
    </PageContainer>
  );

  if (isLoading) return header(<Skeleton />);
  if (isError)
    return header(
      <Card>
        <ErrorState message="Unable to load opportunities." onRetry={() => refetch()} />
      </Card>,
    );
  if (isEmpty || base.length === 0)
    return header(
      <Card>
        <EmptyState
          title="No opportunities found."
          description="Analyze more leads to identify potential business opportunities."
          action={
            <div className="flex gap-2">
              <Link to="/leads" className="btn-secondary">
                View leads
              </Link>
              <Link to="/leads/analyze" className="btn-primary">
                Analyze new lead
              </Link>
            </div>
          }
        />
      </Card>,
    );

  return header(
    <div className="space-y-4">
      <OpportunitySummary summary={summary} />

      <QuickFilterTabs opportunities={base} filters={filters} onApply={updateParams} />

      <OpportunityFilters
        filters={filters}
        searchText={searchText}
        onSearchText={setSearchText}
        onChange={updateParams}
        onClear={handleClear}
      />

      {datasetLimited && (
        <p className="text-xs text-slate-400 dark:text-slate-500">
          Derived from the top {fetchedCount} of {serverTotal?.toLocaleString()} leads.
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {visible.length} opportunit{visible.length === 1 ? 'y' : 'ies'}
            </p>
            <Select
              label=""
              aria-label="Sort by"
              value={sortBy}
              className="w-auto py-1"
              onChange={(e) => updateParams({ sort: e.target.value as OpportunitySortBy })}
            >
              <option value="score">Sort: Score</option>
              <option value="urgency">Sort: Urgency</option>
              <option value="team">Sort: Estimated team</option>
              <option value="signal_date">Sort: Signal date</option>
              <option value="created">Sort: Created date</option>
            </Select>
          </div>

          {visible.length === 0 ? (
            <Card>
              <EmptyState
                title="No opportunities match your filters"
                description="Try adjusting or clearing your filters."
                action={
                  hasActiveFilters ? (
                    <button type="button" className="btn-secondary" onClick={handleClear}>
                      Clear filters
                    </button>
                  ) : undefined
                }
              />
            </Card>
          ) : (
            <>
              {/* Desktop / tablet table */}
              <div className="hidden lg:block">
                <Card padded={false}>
                  <OpportunityTable opportunities={visible} onOpen={setSelected} />
                </Card>
              </div>
              {/* Mobile cards */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:hidden">
                {visible.map((o) => (
                  <OpportunityCard key={o.leadId} opportunity={o} onOpen={setSelected} />
                ))}
              </div>
            </>
          )}
        </div>

        <div className="space-y-4">
          <TopOpportunities opportunities={base} onOpen={setSelected} />
          <OpportunityChart data={distribution} />
        </div>
      </div>

      <OpportunityDetailDrawer opportunity={selected} onClose={() => setSelected(null)} />
    </div>,
  );
}
