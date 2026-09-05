import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { cn } from '@/utils/cn';
import { ContactSummaryCards } from '@/components/contacts/ContactSummaryCards';
import { ContactFilters } from '@/components/contacts/ContactFilters';
import { ContactTable } from '@/components/contacts/ContactTable';
import { ContactCard } from '@/components/contacts/ContactCard';
import { CompanyRoleGroup } from '@/components/contacts/CompanyRoleGroup';
import { TopTargetRoles } from '@/components/contacts/TopTargetRoles';
import { ContactRecommendationDetails } from '@/components/contacts/ContactRecommendationDetails';
import { useDebounce } from '@/hooks/useDebounce';
import { useContacts } from '@/hooks/useContacts';
import {
  buildContactSummary,
  buildTopTargetRoles,
  filterContacts,
  groupByCompany,
  sortContacts,
} from '@/services/contacts';
import type {
  ContactFilterState,
  ContactRecommendation,
  ContactSortBy,
} from '@/types/contact';

type View = 'table' | 'company';

function parseFilters(sp: URLSearchParams): ContactFilterState {
  const g = (k: string) => sp.get(k) ?? '';
  return {
    search: g('search'),
    type: g('type') as ContactFilterState['type'],
    role: g('role'),
    priority: g('priority') as ContactFilterState['priority'],
    industry: g('industry'),
    opportunityType: g('opportunityType') as ContactFilterState['opportunityType'],
    confidence: g('confidence') as ContactFilterState['confidence'],
    minRelevance: g('minRelevance'),
  };
}

function Skeleton() {
  return (
    <div className="space-y-4" aria-hidden="true" data-testid="contacts-skeleton">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-20 animate-pulse rounded-xl bg-slate-100" />
        ))}
      </div>
      <div className="h-20 animate-pulse rounded-xl bg-slate-100" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="h-96 animate-pulse rounded-xl bg-slate-100 lg:col-span-2" />
        <div className="h-96 animate-pulse rounded-xl bg-slate-100" />
      </div>
    </div>
  );
}

export function ContactsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => parseFilters(searchParams), [searchParams]);
  const sortBy = (searchParams.get('sort') as ContactSortBy) || 'relevance';
  const view = (searchParams.get('view') as View) || 'table';

  const [searchText, setSearchText] = useState(filters.search);
  const debouncedSearch = useDebounce(searchText, 350);
  const [selected, setSelected] = useState<ContactRecommendation | null>(null);

  const { contacts, isLoading, isError, isFetching, refetch, isEmpty, datasetLimited, serverTotal, fetchedCount } =
    useContacts();

  const updateParams = (patch: Partial<ContactFilterState> & { sort?: ContactSortBy; view?: View }) => {
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

  const effectiveFilters: ContactFilterState = { ...filters, search: debouncedSearch };
  const base = useMemo(() => contacts ?? [], [contacts]);
  const visible = useMemo(
    () => sortContacts(filterContacts(base, effectiveFilters), sortBy),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [base, searchParams, debouncedSearch, sortBy],
  );
  const summary = useMemo(() => buildContactSummary(base), [base]);
  const topRoles = useMemo(() => buildTopTargetRoles(base), [base]);
  const groups = useMemo(() => groupByCompany(visible), [visible]);

  const hasActiveFilters =
    Boolean(debouncedSearch) ||
    (['type', 'role', 'priority', 'industry', 'opportunityType', 'confidence', 'minRelevance'] as const).some(
      (k) => filters[k] !== '',
    );

  const handleClear = () => {
    setSearchText('');
    const next = new URLSearchParams();
    if (view !== 'table') next.set('view', view);
    setSearchParams(next, { replace: true });
  };

  const actions = (
    <div className="flex items-center gap-2">
      <button
        type="button"
        className="btn-secondary text-sm"
        onClick={() => refetch()}
        disabled={isFetching}
        aria-label="Refresh recommendations"
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
      title="Contacts"
      subtitle="Identify the decision-maker roles most relevant to each business opportunity."
      actions={actions}
    >
      {children}
    </PageContainer>
  );

  if (isLoading) return header(<Skeleton />);
  if (isError)
    return header(
      <Card>
        <ErrorState message="Unable to load decision-maker recommendations." onRetry={() => refetch()} />
      </Card>,
    );
  if (isEmpty || base.length === 0)
    return header(
      <Card>
        <EmptyState
          title="No decision-maker recommendations yet."
          description="Analyze more leads to identify relevant decision-maker roles."
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
      <ContactSummaryCards summary={summary} />
      <p className="text-xs text-slate-400">
        Phase 1 shows recommended decision-maker <strong>roles</strong>, not verified people.
        Relevance reflects the related lead's opportunity score.
      </p>

      <ContactFilters
        filters={filters}
        searchText={searchText}
        onSearchText={setSearchText}
        onChange={updateParams}
        onClear={handleClear}
      />

      {datasetLimited && (
        <p className="text-xs text-slate-400">
          Derived from the top {fetchedCount} of {serverTotal?.toLocaleString()} leads.
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="inline-flex rounded-md border border-slate-200 p-0.5" role="tablist" aria-label="View">
              {(['table', 'company'] as View[]).map((v) => (
                <button
                  key={v}
                  type="button"
                  role="tab"
                  aria-selected={view === v}
                  onClick={() => updateParams({ view: v })}
                  className={cn(
                    'rounded px-3 py-1 text-sm',
                    view === v ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-50',
                  )}
                >
                  {v === 'table' ? 'Table' : 'By company'}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-3">
              <p className="text-sm text-slate-500">
                {visible.length} recommendation{visible.length === 1 ? '' : 's'}
              </p>
              <Select
                aria-label="Sort by"
                value={sortBy}
                className="w-auto py-1"
                onChange={(e) => updateParams({ sort: e.target.value as ContactSortBy })}
              >
                <option value="relevance">Sort: Relevance</option>
                <option value="company">Sort: Company</option>
                <option value="lead_score">Sort: Lead score</option>
                <option value="priority">Sort: Priority</option>
                <option value="updated">Sort: Updated</option>
              </Select>
            </div>
          </div>

          {visible.length === 0 ? (
            <Card>
              <EmptyState
                title="No recommendations match your filters"
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
          ) : view === 'company' ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {groups.map((g) => (
                <CompanyRoleGroup key={g.company} group={g} onOpen={setSelected} />
              ))}
            </div>
          ) : (
            <>
              <div className="hidden lg:block">
                <Card padded={false}>
                  <ContactTable contacts={visible} onOpen={setSelected} />
                </Card>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:hidden">
                {visible.map((c) => (
                  <ContactCard key={c.id} contact={c} onOpen={setSelected} />
                ))}
              </div>
            </>
          )}
        </div>

        <div className="space-y-4">
          <TopTargetRoles roles={topRoles} />
        </div>
      </div>

      <ContactRecommendationDetails contact={selected} onClose={() => setSelected(null)} />
    </div>,
  );
}
