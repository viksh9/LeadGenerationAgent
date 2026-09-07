import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { CompaniesTable } from '@/components/companies/CompaniesTable';
import { useCompanies } from '@/hooks/useCompanies';
import type { CompanySortBy, CompanySummary } from '@/types/company';

function SkeletonRows() {
  return (
    <div className="space-y-2 p-4" aria-hidden="true" data-testid="companies-skeleton">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-10 w-full animate-pulse rounded bg-slate-100 dark:bg-slate-800" />
      ))}
    </div>
  );
}

function sortCompanies(companies: CompanySummary[], sortBy: CompanySortBy): CompanySummary[] {
  const copy = [...companies];
  if (sortBy === 'name') return copy.sort((a, b) => a.name.localeCompare(b.name));
  if (sortBy === 'leads') return copy.sort((a, b) => b.leadCount - a.leadCount);
  return copy.sort((a, b) => b.bestScore - a.bestScore);
}

export function CompaniesPage() {
  const { companies, isLoading, isError, refetch, isEmpty, datasetLimited, fetchedCount, serverTotal } =
    useCompanies();
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState<CompanySortBy>('score');

  const visible = useMemo(() => {
    if (!companies) return [];
    const term = search.trim().toLowerCase();
    const filtered = term
      ? companies.filter(
          (c) => c.name.toLowerCase().includes(term) || (c.industry ?? '').toLowerCase().includes(term),
        )
      : companies;
    return sortCompanies(filtered, sortBy);
  }, [companies, search, sortBy]);

  let body;
  if (isLoading) {
    body = <SkeletonRows />;
  } else if (isError) {
    body = <ErrorState message="Unable to load companies." onRetry={() => refetch()} />;
  } else if (isEmpty || !companies) {
    body = (
      <EmptyState
        title="No companies yet"
        description="Analyze your first lead to start building your company directory."
      />
    );
  } else if (visible.length === 0) {
    body = <EmptyState title="No companies match your search" description="Try a different term." />;
  } else {
    body = <CompaniesTable companies={visible} />;
  }

  const countLabel =
    companies && companies.length > 0
      ? `${companies.length} compan${companies.length === 1 ? 'y' : 'ies'} across ${fetchedCount} lead${fetchedCount === 1 ? '' : 's'}`
      : null;

  const showControls = !isLoading && !isError && companies && companies.length > 0;

  return (
    <PageContainer
      title="Companies"
      subtitle="Research target accounts and identify organizations with active business opportunities."
    >
      <div className="space-y-4">
        {countLabel && <p className="text-sm text-slate-500 dark:text-slate-400">{countLabel}</p>}
        {showControls && (
          <div className="card card-pad">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="sm:col-span-2">
                <label className="label" htmlFor="company-search">
                  Search
                </label>
                <div className="relative">
                  <Search
                    className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500"
                    aria-hidden="true"
                  />
                  <input
                    id="company-search"
                    className="input pl-9"
                    placeholder="Company or industry…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
              </div>
              <Select
                label="Sort by"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as CompanySortBy)}
              >
                <option value="score">Best score</option>
                <option value="leads">Lead count</option>
                <option value="name">Company name</option>
              </Select>
            </div>
            {datasetLimited && (
              <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">
                Aggregated from the top {fetchedCount} of {serverTotal?.toLocaleString()} leads.
              </p>
            )}
          </div>
        )}
        <Card padded={false}>{body}</Card>
      </div>
    </PageContainer>
  );
}
