import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Plus, RefreshCw } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { ActiveFilters } from '@/components/leads/ActiveFilters';
import { LeadsFilters } from '@/components/leads/LeadsFilters';
import { LeadsPagination } from '@/components/leads/LeadsPagination';
import { LeadsTable } from '@/components/leads/LeadsTable';
import { useDebounce } from '@/hooks/useDebounce';
import { useDeleteLead, useLeads } from '@/hooks/useLeads';
import { type SortBy, type SortOrder } from '@/constants/leads';
import { getPreferences } from '@/services/preferences';
import type { Lead, LeadListParams, LeadPriority, LeadStatus, SignalType } from '@/types/lead';

const FILTER_KEYS: (keyof LeadListParams)[] = [
  'search',
  'industry',
  'location',
  'signal_type',
  'lead_priority',
  'status',
  'min_score',
  'max_score',
  'technology',
];

function parseParams(sp: URLSearchParams): LeadListParams {
  const str = (k: string) => sp.get(k) || undefined;
  const num = (k: string) => {
    const v = sp.get(k);
    if (v === null || v === '') return undefined;
    const n = Number(v);
    return Number.isFinite(n) ? n : undefined;
  };
  return {
    page: num('page') ?? 1,
    page_size: num('page_size') ?? getPreferences().leadsPageSize,
    search: str('search'),
    industry: str('industry'),
    location: str('location'),
    signal_type: str('signal_type') as SignalType | undefined,
    lead_priority: str('lead_priority') as LeadPriority | undefined,
    status: str('status') as LeadStatus | undefined,
    min_score: num('min_score'),
    max_score: num('max_score'),
    technology: str('technology'),
    sort_by: (str('sort_by') as SortBy) ?? 'lead_score',
    sort_order: (str('sort_order') as SortOrder) ?? 'desc',
  };
}

function SkeletonRows() {
  return (
    <div className="space-y-2 p-4" aria-hidden="true" data-testid="leads-skeleton">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-10 w-full animate-pulse rounded bg-slate-100" />
      ))}
    </div>
  );
}

export function LeadsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const params = useMemo(() => parseParams(searchParams), [searchParams]);

  const [searchText, setSearchText] = useState(params.search ?? '');
  const debouncedSearch = useDebounce(searchText, 350);
  const [pendingDelete, setPendingDelete] = useState<Lead | null>(null);

  const deleteMutation = useDeleteLead();

  const updateParams = (patch: Partial<LeadListParams>) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(patch)) {
          if (value === undefined || value === '' || value === null) next.delete(key);
          else next.set(key, String(value));
        }
        // Any change except explicit paging returns to page 1.
        if (!('page' in patch)) next.set('page', '1');
        return next;
      },
      { replace: true },
    );
  };

  // Push the debounced search into the URL (source of truth for the query).
  useEffect(() => {
    if (debouncedSearch !== (searchParams.get('search') ?? '')) {
      updateParams({ search: debouncedSearch || undefined });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  const query = useLeads(params);
  const data = query.data;

  const activeFilterCount = FILTER_KEYS.filter((k) => params[k] !== undefined).length;

  const handleClear = () => {
    setSearchText('');
    setSearchParams(new URLSearchParams(), { replace: true });
  };

  const handleRemoveFilter = (key: keyof LeadListParams) => {
    if (key === 'search') setSearchText('');
    updateParams({ [key]: undefined } as Partial<LeadListParams>);
  };

  const handleSort = (column: SortBy) => {
    const nextOrder: SortOrder =
      params.sort_by === column && params.sort_order === 'desc' ? 'asc' : 'desc';
    updateParams({ sort_by: column, sort_order: nextOrder });
  };

  const confirmDelete = () => {
    if (!pendingDelete) return;
    deleteMutation.mutate(pendingDelete.id, { onSuccess: () => setPendingDelete(null) });
  };

  let results;
  if (query.isLoading) {
    results = <SkeletonRows />;
  } else if (query.isError) {
    results = <ErrorState message="Unable to load leads." onRetry={() => query.refetch()} />;
  } else if (!data || data.items.length === 0) {
    results =
      activeFilterCount > 0 ? (
        <EmptyState
          title="No leads match your current filters"
          description="Try adjusting or clearing your filters."
          action={
            <button type="button" className="btn-secondary" onClick={handleClear}>
              Clear filters
            </button>
          }
        />
      ) : (
        <EmptyState
          title="No leads yet."
          description="Analyze your first lead to start building your sales intelligence."
          action={
            <Link to="/leads/analyze" className="btn-primary">
              <Plus className="h-4 w-4" aria-hidden="true" />
              Analyze New Lead
            </Link>
          }
        />
      );
  } else {
    results = (
      <>
        <div className={query.isFetching ? 'opacity-60 transition-opacity' : undefined}>
          <LeadsTable
            leads={data.items}
            params={params}
            onSort={handleSort}
            onDelete={setPendingDelete}
          />
        </div>
        <LeadsPagination
          page={data.page}
          pageSize={data.page_size}
          total={data.total}
          totalPages={data.total_pages}
          onPage={(page) => updateParams({ page })}
          onPageSize={(size) => updateParams({ page_size: size, page: 1 })}
        />
      </>
    );
  }

  return (
    <PageContainer
      title="Leads"
      subtitle="Discover, qualify, and prioritize your best business opportunities."
      actions={
        <>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => query.refetch()}
            aria-label="Refresh leads"
          >
            <RefreshCw
              className={query.isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
              aria-hidden="true"
            />
            Refresh
          </button>
          <Link to="/leads/analyze" className="btn-primary">
            <Plus className="h-4 w-4" aria-hidden="true" />
            Analyze New Lead
          </Link>
        </>
      }
    >
      <div className="space-y-4">
        <LeadsFilters
          params={params}
          searchText={searchText}
          onSearchTextChange={setSearchText}
          onChange={updateParams}
        />

        <ActiveFilters params={params} onRemove={handleRemoveFilter} onClear={handleClear} />

        {data && (
          <p className="text-sm text-slate-500">
            {data.total.toLocaleString()} lead{data.total === 1 ? '' : 's'}
          </p>
        )}

        <Card padded={false}>{results}</Card>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        destructive
        title="Delete this lead?"
        description={
          pendingDelete
            ? `“${pendingDelete.company_name}” will be permanently removed. This cannot be undone.`
            : undefined
        }
        confirmLabel="Delete"
        busy={deleteMutation.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </PageContainer>
  );
}
