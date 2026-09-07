import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { LeadsPagination } from '@/components/leads/LeadsPagination';
import { useTenders } from '@/hooks/useTenders';
import { tenderStatusDisplay, tenderValueDisplay } from '@/services/tenders';
import { commercialIntentDisplay } from '@/services/signals';
import { formatDate } from '@/utils/format';
import type { TenderListParams } from '@/services/tenders';

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: 'OPEN', label: 'Open' },
  { value: 'CLOSING_SOON', label: 'Closing soon' },
  { value: 'AWARDED', label: 'Awarded' },
  { value: 'CLOSED', label: 'Closed' },
  { value: 'CANCELLED', label: 'Cancelled' },
  { value: 'UNKNOWN', label: 'Unknown' },
];

function num(sp: URLSearchParams, key: string): number | undefined {
  const raw = sp.get(key);
  if (raw === null) return undefined;
  const n = Number(raw);
  return Number.isFinite(n) ? n : undefined;
}

function Skeleton() {
  return (
    <div className="space-y-3" aria-hidden="true" data-testid="tenders-skeleton">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
      ))}
    </div>
  );
}

export function TendersPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const params: TenderListParams = useMemo(
    () => ({
      page: num(searchParams, 'page') ?? 1,
      page_size: num(searchParams, 'page_size') ?? 20,
      status: searchParams.get('status') || undefined,
      technology: searchParams.get('technology') || undefined,
      organization: searchParams.get('organization') || undefined,
      category: searchParams.get('category') || undefined,
    }),
    [searchParams],
  );

  const updateParams = (patch: Record<string, string | number | undefined>) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const [key, value] of Object.entries(patch)) {
          if (value === undefined || value === '' || value === null) next.delete(key);
          else next.set(key, String(value));
        }
        if (!('page' in patch)) next.set('page', '1');
        return next;
      },
      { replace: true },
    );
  };

  const { data, isLoading, isError, isFetching, refetch } = useTenders(params);

  const actions = (
    <button
      type="button"
      className="btn-secondary text-sm"
      onClick={() => refetch()}
      disabled={isFetching}
      aria-label="Refresh tenders"
    >
      <RefreshCw className={isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
      Refresh
    </button>
  );

  const header = (children: React.ReactNode) => (
    <PageContainer
      title="Tenders"
      subtitle="Public tenders and procurement opportunities collected from real sources."
      actions={actions}
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Select
            label="Status"
            value={params.status ?? ''}
            onChange={(e) => updateParams({ status: e.target.value })}
          >
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </div>
        {children}
      </div>
    </PageContainer>
  );

  if (isLoading) return header(<Skeleton />);
  if (isError)
    return header(
      <Card>
        <ErrorState message="Unable to load tenders." onRetry={() => refetch()} />
      </Card>,
    );

  const items = data?.items ?? [];
  if (items.length === 0)
    return header(
      <Card>
        <EmptyState
          title="No tenders available yet."
          description="No tenders match the current filters, or none have been collected yet."
        />
      </Card>,
    );

  return header(
    <Card padded={false}>
      <ul className="divide-y divide-slate-100 dark:divide-slate-800">
        {items.map((t) => {
          const status = tenderStatusDisplay(t.tender_status);
          const intent = commercialIntentDisplay(t.commercial_intent);
          return (
            <li key={t.id} className="px-5 py-4">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{t.title}</p>
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                    {t.organization_name}
                    {t.department ? ` • ${t.department}` : ''}
                  </p>
                </div>
                <span className={`badge ${status.className}`}>{status.label}</span>
              </div>

              {t.scope_summary && (
                <p className="mt-1 line-clamp-2 text-sm text-slate-500 dark:text-slate-400">
                  {t.scope_summary}
                </p>
              )}

              {t.technologies.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {t.technologies.map((tech) => (
                    <span
                      key={tech}
                      className="badge bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"
                    >
                      {tech}
                    </span>
                  ))}
                </div>
              )}

              <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-slate-400 dark:text-slate-500">
                <span>
                  Closes:{' '}
                  <span className="font-medium text-slate-600 dark:text-slate-300">
                    {formatDate(t.closing_date)}
                  </span>
                </span>
                <span>
                  Est. value:{' '}
                  <span className="font-medium text-slate-600 dark:text-slate-300">
                    {tenderValueDisplay(t)}
                  </span>
                </span>
                <span className="flex items-center gap-1">
                  Commercial intent:{' '}
                  <span className={`badge ${intent.className}`}>{intent.label}</span>
                </span>
                {t.source_url && (
                  <a
                    href={t.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-auto inline-flex items-center gap-1 text-brand-600 hover:underline"
                  >
                    View source
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                  </a>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {data && (
        <LeadsPagination
          page={data.page}
          pageSize={data.page_size}
          total={data.total}
          totalPages={data.total_pages}
          onPage={(page) => updateParams({ page })}
          onPageSize={(size) => updateParams({ page_size: size, page: 1 })}
        />
      )}
    </Card>,
  );
}
