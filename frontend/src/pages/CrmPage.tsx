import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { RefreshCw, Search } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';
import { Table, Td, Th } from '@/components/ui/Table';
import { Badge, PriorityBadge } from '@/components/ui/Badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/States';
import { cn } from '@/utils/cn';
import { formatDateTime, formatScore } from '@/utils/format';
import { useDebounce } from '@/hooks/useDebounce';
import { useLeads } from '@/hooks/useLeads';
import { useFollowUps, useSetFollowUpStatus } from '@/hooks/useCrm';
import { useProviderStatus } from '@/hooks/useOutreachApi';
import { PRIORITIES, STATUSES } from '@/constants/leads';
import { followUpStatusDisplay, followUpTypeLabel } from '@/services/crm';
import type { LeadListParams, LeadPriority, LeadStatus } from '@/types/lead';

function ProviderSummary() {
  const provider = useProviderStatus();
  if (provider.isLoading)
    return <p className="text-xs text-slate-500 dark:text-slate-400">Checking providers…</p>;
  if (provider.isError || !provider.data)
    return (
      <p className="text-xs text-rose-600 dark:text-rose-400">
        Unable to load provider status.
      </p>
    );
  const p = provider.data;
  const notConfigured = p.email_status === 'NOT_CONFIGURED';
  return (
    <span
      className={cn(
        'badge',
        notConfigured
          ? 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300'
          : 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300',
      )}
    >
      Email: {p.email_provider ?? 'None'} · {p.email_status}
    </span>
  );
}

function FollowUpsCard() {
  const followUps = useFollowUps({ status: 'OPEN' });
  const setStatus = useSetFollowUpStatus();

  return (
    <Card padded={false}>
      <h3 className="border-b border-slate-100 px-5 py-3 text-sm font-semibold text-slate-900 dark:border-slate-800 dark:text-slate-100">
        Open follow-ups
      </h3>
      <div className="px-5 py-4">
        {followUps.isLoading ? (
          <LoadingState message="Loading follow-ups…" />
        ) : followUps.isError ? (
          <ErrorState message="Unable to load follow-ups." onRetry={() => followUps.refetch()} />
        ) : (followUps.data?.items ?? []).length === 0 ? (
          <EmptyState title="No sales activity recorded." />
        ) : (
          <ul className="space-y-3">
            {followUps.data!.items.map((task) => {
              const st = followUpStatusDisplay(task.status);
              return (
                <li key={task.id} className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-800 dark:text-slate-200">
                      {task.title}
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {followUpTypeLabel(task.task_type)}
                      {task.due_at ? ` · due ${formatDateTime(task.due_at)}` : ''}
                      {task.lead_id ? (
                        <>
                          {' · '}
                          <Link to={`/leads/${task.lead_id}`} className="hover:underline">
                            lead #{task.lead_id}
                          </Link>
                        </>
                      ) : null}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className={cn('badge', st.className)}>{st.label}</span>
                    <button
                      type="button"
                      className="btn-ghost text-xs"
                      disabled={setStatus.isPending}
                      onClick={() => setStatus.mutate({ id: task.id, status: 'COMPLETED' })}
                    >
                      Done
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </Card>
  );
}

export function CrmPage() {
  const [searchText, setSearchText] = useState('');
  const [status, setStatus] = useState<LeadStatus | ''>('');
  const [priority, setPriority] = useState<LeadPriority | ''>('');
  const debouncedSearch = useDebounce(searchText, 350);

  const params = useMemo<LeadListParams>(
    () => ({
      page: 1,
      page_size: 50,
      search: debouncedSearch || undefined,
      status: status || undefined,
      lead_priority: priority || undefined,
      sort_by: 'lead_score',
      sort_order: 'desc',
    }),
    [debouncedSearch, status, priority],
  );

  const query = useLeads(params);
  const leads = query.data?.items ?? [];

  const actions = (
    <button
      type="button"
      className="btn-secondary text-sm"
      onClick={() => query.refetch()}
      disabled={query.isFetching}
      aria-label="Refresh CRM"
    >
      <RefreshCw className={query.isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
      Refresh
    </button>
  );

  return (
    <PageContainer
      title="CRM"
      subtitle="Accounts and leads with their real CRM status — open a lead for its timeline and next best action."
      actions={actions}
    >
      <div className="mb-4 flex items-center justify-end">
        <ProviderSummary />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <div className="card card-pad mb-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="sm:col-span-1">
                <label className="label" htmlFor="crm-search">
                  Search
                </label>
                <div className="relative">
                  <Search
                    className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500"
                    aria-hidden="true"
                  />
                  <input
                    id="crm-search"
                    className="input pl-9"
                    placeholder="Search accounts…"
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                  />
                </div>
              </div>
              <Select
                label="Status"
                value={status}
                onChange={(e) => setStatus(e.target.value as LeadStatus | '')}
              >
                <option value="">All statuses</option>
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </Select>
              <Select
                label="Priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value as LeadPriority | '')}
              >
                <option value="">All priorities</option>
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          <Card padded={false}>
            {query.isLoading ? (
              <LoadingState message="Loading accounts…" />
            ) : query.isError ? (
              <ErrorState message="Unable to load CRM accounts." onRetry={() => query.refetch()} />
            ) : leads.length === 0 ? (
              <EmptyState title="No verified business contacts available." />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <Th>Account</Th>
                    <Th>Lead score</Th>
                    <Th>Evidence confidence</Th>
                    <Th>Status</Th>
                    <Th>Priority</Th>
                  </tr>
                </thead>
                <tbody>
                  {leads.map((lead) => (
                    <tr key={lead.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40">
                      <Td>
                        <Link
                          to={`/leads/${lead.id}`}
                          className="font-medium text-slate-900 hover:underline dark:text-slate-100"
                        >
                          {lead.company_name}
                        </Link>
                        {lead.industry && (
                          <p className="text-xs text-slate-400 dark:text-slate-500">{lead.industry}</p>
                        )}
                      </Td>
                      <Td>{formatScore(lead.lead_score)}</Td>
                      <Td>
                        {lead.evidence_confidence === undefined || lead.evidence_confidence === null
                          ? 'Not available'
                          : formatScore(lead.evidence_confidence)}
                      </Td>
                      <Td>
                        <Badge>{lead.status}</Badge>
                      </Td>
                      <Td>
                        <PriorityBadge priority={lead.lead_priority} />
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>
        </div>

        <div>
          <FollowUpsCard />
        </div>
      </div>
    </PageContainer>
  );
}
