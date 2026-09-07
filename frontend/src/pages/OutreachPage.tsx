import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { OutreachSummaryCards } from '@/components/outreach/OutreachSummaryCards';
import { OutreachFilters } from '@/components/outreach/OutreachFilters';
import { OutreachTable } from '@/components/outreach/OutreachTable';
import { OutreachCard } from '@/components/outreach/OutreachCard';
import { OutreachDetailDrawer } from '@/components/outreach/OutreachDetailDrawer';
import { FollowUpQueue } from '@/components/outreach/FollowUpQueue';
import { useDebounce } from '@/hooks/useDebounce';
import { useOutreach } from '@/hooks/useOutreach';
import {
  buildOutreachSummary,
  filterOutreach,
  sortOutreach,
  splitQueue,
} from '@/services/outreach';
import type { OutreachFilterState, OutreachItem, OutreachSortBy } from '@/types/outreach';

function parseFilters(sp: URLSearchParams): OutreachFilterState {
  const g = (k: string) => sp.get(k) ?? '';
  return {
    search: g('search'),
    priority: g('priority') as OutreachFilterState['priority'],
    industry: g('industry'),
    opportunityType: g('opportunityType') as OutreachFilterState['opportunityType'],
    role: g('role'),
    status: g('status') as OutreachFilterState['status'],
    minScore: g('minScore'),
  };
}

function Skeleton() {
  return (
    <div className="space-y-4" aria-hidden="true" data-testid="outreach-skeleton">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-20 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
        ))}
      </div>
      <div className="h-20 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="h-96 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800 lg:col-span-2" />
        <div className="h-40 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
      </div>
    </div>
  );
}

function QueueSection({
  title,
  items,
  onOpen,
  emptyText,
}: {
  title: string;
  items: OutreachItem[];
  onOpen: (item: OutreachItem) => void;
  emptyText: string;
}) {
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
        {title} ({items.length})
      </h3>
      {items.length === 0 ? (
        <Card>
          <p className="p-5 text-sm text-slate-400 dark:text-slate-500">{emptyText}</p>
        </Card>
      ) : (
        <>
          <div className="hidden lg:block">
            <Card padded={false}>
              <OutreachTable items={items} onOpen={onOpen} />
            </Card>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:hidden">
            {items.map((o) => (
              <OutreachCard key={o.leadId} item={o} onOpen={onOpen} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export function OutreachPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => parseFilters(searchParams), [searchParams]);
  const sortBy = (searchParams.get('sort') as OutreachSortBy) || 'priority';

  const [searchText, setSearchText] = useState(filters.search);
  const debouncedSearch = useDebounce(searchText, 350);
  const [selected, setSelected] = useState<OutreachItem | null>(null);

  const { items, isLoading, isError, isFetching, refetch, isEmpty, datasetLimited, serverTotal, fetchedCount } =
    useOutreach();

  const updateParams = (patch: Partial<OutreachFilterState> & { sort?: OutreachSortBy }) => {
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
    if (debouncedSearch !== (searchParams.get('search') ?? '')) updateParams({ search: debouncedSearch });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  const effectiveFilters: OutreachFilterState = { ...filters, search: debouncedSearch };
  const base = useMemo(() => items ?? [], [items]);
  const filtered = useMemo(
    () => filterOutreach(base, effectiveFilters),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [base, searchParams, debouncedSearch],
  );
  const { ready, needsReview } = useMemo(() => {
    const split = splitQueue(filtered);
    return {
      ready: sortOutreach(split.ready, sortBy),
      needsReview: sortOutreach(split.needsReview, sortBy),
    };
  }, [filtered, sortBy]);
  const summary = useMemo(() => buildOutreachSummary(base), [base]);

  const hasActiveFilters =
    Boolean(debouncedSearch) ||
    (['priority', 'industry', 'opportunityType', 'role', 'status', 'minScore'] as const).some(
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
        aria-label="Refresh outreach"
      >
        <RefreshCw className={isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
        Refresh
      </button>
      <Link to="/opportunities?priority=HOT" className="btn-secondary text-sm">
        View hot opportunities
      </Link>
    </div>
  );

  const header = (children: React.ReactNode) => (
    <PageContainer
      title="Outreach"
      subtitle="Review personalized messaging and prepare outreach for qualified opportunities."
      actions={actions}
    >
      {children}
    </PageContainer>
  );

  if (isLoading) return header(<Skeleton />);
  if (isError)
    return header(
      <Card>
        <ErrorState message="Unable to load outreach opportunities." onRetry={() => refetch()} />
      </Card>,
    );
  if (isEmpty || base.length === 0)
    return header(
      <Card>
        <EmptyState
          title="No outreach opportunities are ready yet."
          description="Analyze and qualify leads before preparing outreach."
          action={
            <Link to="/leads" className="btn-secondary">
              View leads
            </Link>
          }
        />
      </Card>,
    );

  const noMatches = ready.length === 0 && needsReview.length === 0;

  return header(
    <div className="space-y-4">
      <OutreachSummaryCards summary={summary} />
      <p className="text-xs text-slate-400 dark:text-slate-500">
        Prepare and copy messaging for human-reviewed outreach — nothing is sent from here.
      </p>

      <OutreachFilters
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

      <div className="flex items-center justify-end">
        <Select
          aria-label="Sort by"
          value={sortBy}
          className="w-auto py-1"
          onChange={(e) => updateParams({ sort: e.target.value as OutreachSortBy })}
        >
          <option value="priority">Sort: Priority</option>
          <option value="score">Sort: Lead score</option>
          <option value="company">Sort: Company</option>
          <option value="opportunity">Sort: Opportunity</option>
          <option value="created">Sort: Created</option>
          <option value="signal_date">Sort: Signal date</option>
        </Select>
      </div>

      {noMatches ? (
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
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            {ready.length === 0 && needsReview.length > 0 && (
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Some opportunities need additional research before outreach.
              </p>
            )}
            <QueueSection
              title="Ready for outreach"
              items={ready}
              onOpen={setSelected}
              emptyText="No leads are ready for outreach with the current filters."
            />
            <QueueSection
              title="Needs review"
              items={needsReview}
              onOpen={setSelected}
              emptyText="Nothing needs review — all filtered leads are outreach-ready."
            />
          </div>
          <div className="space-y-4">
            <FollowUpQueue />
          </div>
        </div>
      )}

      <OutreachDetailDrawer item={selected} onClose={() => setSelected(null)} />
    </div>,
  );
}
