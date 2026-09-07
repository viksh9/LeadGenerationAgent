import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ExternalLink, RefreshCw } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { LeadsPagination } from '@/components/leads/LeadsPagination';
import { useDebounce } from '@/hooks/useDebounce';
import { useSignals } from '@/hooks/useSignals';
import { commercialIntentDisplay, signalStrengthDisplay } from '@/services/signals';
import { SIGNAL_LABELS, SIGNAL_TYPES } from '@/constants/leads';
import { formatDate } from '@/utils/format';
import type { SignalListParams } from '@/services/signals';

function num(sp: URLSearchParams, key: string): number | undefined {
  const raw = sp.get(key);
  if (raw === null) return undefined;
  const n = Number(raw);
  return Number.isFinite(n) ? n : undefined;
}

function Skeleton() {
  return (
    <div className="space-y-3" aria-hidden="true" data-testid="signals-skeleton">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
      ))}
    </div>
  );
}

export function SignalsPage() {
  const [searchParams, setSearchParams] = useSearchParams();

  const params: SignalListParams = useMemo(
    () => ({
      page: num(searchParams, 'page') ?? 1,
      page_size: num(searchParams, 'page_size') ?? 20,
      signal_type: searchParams.get('signal_type') || undefined,
      technology: searchParams.get('technology') || undefined,
      company: searchParams.get('company') || undefined,
      source: searchParams.get('source') || undefined,
    }),
    [searchParams],
  );

  const [companyText, setCompanyText] = useState(params.company ?? '');
  const [techText, setTechText] = useState(params.technology ?? '');
  const debouncedCompany = useDebounce(companyText, 350);
  const debouncedTech = useDebounce(techText, 350);

  const updateParams = (patch: Record<string, string | number | undefined>) => {
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

  useEffect(() => {
    if (debouncedCompany !== (searchParams.get('company') ?? '')) {
      updateParams({ company: debouncedCompany });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedCompany]);

  useEffect(() => {
    if (debouncedTech !== (searchParams.get('technology') ?? '')) {
      updateParams({ technology: debouncedTech });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedTech]);

  const { data, isLoading, isError, isFetching, refetch } = useSignals(params);

  const actions = (
    <button
      type="button"
      className="btn-secondary text-sm"
      onClick={() => refetch()}
      disabled={isFetching}
      aria-label="Refresh signals"
    >
      <RefreshCw className={isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
      Refresh
    </button>
  );

  const header = (children: React.ReactNode) => (
    <PageContainer
      title="Business signals"
      subtitle="Verified demand and intent signals collected from real sources."
      actions={actions}
    >
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <Input
            label="Search company"
            placeholder="Company name"
            value={companyText}
            onChange={(e) => setCompanyText(e.target.value)}
          />
          <Input
            label="Technology"
            placeholder="e.g. Java"
            value={techText}
            onChange={(e) => setTechText(e.target.value)}
          />
          <Select
            label="Signal type"
            value={params.signal_type ?? ''}
            onChange={(e) => updateParams({ signal_type: e.target.value })}
          >
            <option value="">All types</option>
            {SIGNAL_TYPES.map((t) => (
              <option key={t} value={t}>
                {SIGNAL_LABELS[t]}
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
        <ErrorState message="Unable to load business signals." onRetry={() => refetch()} />
      </Card>,
    );

  const items = data?.items ?? [];
  if (items.length === 0)
    return header(
      <Card>
        <EmptyState
          title="No verified signals available yet."
          description="No signals match the current filters, or none have been collected yet."
        />
      </Card>,
    );

  return header(
    <Card padded={false}>
      <ul className="divide-y divide-slate-100 dark:divide-slate-800">
        {items.map((s) => {
          const strength = signalStrengthDisplay(s.signal_strength);
          const intent = commercialIntentDisplay(s.commercial_intent);
          return (
            <li key={s.id} className="px-5 py-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
                    {s.company_name ?? 'Unknown company'}
                  </span>
                  <span className="badge bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                    {s.signal_type}
                  </span>
                  <span className={`badge ${strength.className}`}>{strength.label}</span>
                </div>
                <span className="text-xs text-slate-400 dark:text-slate-500">
                  {formatDate(s.published_at)}
                </span>
              </div>

              {s.signal_title && (
                <p className="mt-1 text-sm font-medium text-slate-800 dark:text-slate-200">
                  {s.signal_title}
                </p>
              )}
              {s.signal_description && (
                <p className="mt-0.5 line-clamp-2 text-sm text-slate-500 dark:text-slate-400">
                  {s.signal_description}
                </p>
              )}

              {s.technologies.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {s.technologies.map((t) => (
                    <span
                      key={t}
                      className="badge bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"
                    >
                      {t}
                    </span>
                  ))}
                </div>
              )}

              <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-slate-400 dark:text-slate-500">
                <span>
                  Source:{' '}
                  <span className="font-medium text-slate-600 dark:text-slate-300">{s.source_id}</span>
                  {s.source_count > 1 && ` (+${s.source_count - 1} more)`}
                </span>
                <span>
                  Evidence confidence:{' '}
                  <span className="font-medium tabular-nums text-slate-600 dark:text-slate-300">
                    {Math.round(s.evidence_confidence)}
                  </span>
                </span>
                <span className="flex items-center gap-1">
                  Commercial intent:{' '}
                  <span className={`badge ${intent.className}`}>{intent.label}</span>
                </span>
                {s.signal_url && (
                  <a
                    href={s.signal_url}
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
