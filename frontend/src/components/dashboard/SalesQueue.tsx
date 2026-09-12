import { Link } from 'react-router-dom';
import { Card } from '@/components/ui/Card';
import { PriorityBadge } from '@/components/ui/Badge';
import { useFollowUps } from '@/hooks/useCrm';
import { useLeads } from '@/hooks/useLeads';
import { formatDate } from '@/utils/format';

/**
 * Sales queue (§18/§20) — leads/tasks needing attention, entirely database-driven.
 * "Follow-ups due" reads real OPEN FollowUpTasks; "Needs attention" reads real
 * high-priority new leads. Both use honest empty states and never fabricate rows.
 */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
      <div className="mt-2">{children}</div>
    </div>
  );
}

export function SalesQueue() {
  const followUps = useFollowUps({ status: 'OPEN' });
  const attention = useLeads({ lead_priority: 'HOT', status: 'NEW', page_size: 5,
    sort_by: 'lead_score', sort_order: 'desc' });

  const dueItems = (followUps.data?.items ?? []).slice(0, 6);
  const attentionItems = attention.data?.items ?? [];

  return (
    <Card>
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
        <Section title="Follow-ups due">
          {followUps.isLoading ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>
          ) : followUps.isError ? (
            <p className="text-sm text-rose-600 dark:text-rose-400">Unable to load follow-ups.</p>
          ) : dueItems.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">No follow-ups are due.</p>
          ) : (
            <ul className="space-y-2">
              {dueItems.map((t) => (
                <li key={t.id} className="text-sm">
                  {t.lead_id ? (
                    <Link to={`/leads/${t.lead_id}`} className="text-brand-600 hover:underline">{t.title}</Link>
                  ) : (
                    <span className="text-slate-800 dark:text-slate-200">{t.title}</span>
                  )}
                  <span className="ml-2 text-xs text-slate-400 dark:text-slate-500">
                    {t.due_at ? `due ${formatDate(t.due_at)}` : 'no due date'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Needs attention">
          {attention.isLoading ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>
          ) : attention.isError ? (
            <p className="text-sm text-rose-600 dark:text-rose-400">Unable to load leads.</p>
          ) : attentionItems.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">No leads need attention.</p>
          ) : (
            <ul className="space-y-2">
              {attentionItems.map((l) => (
                <li key={l.id} className="flex items-center justify-between gap-2 text-sm">
                  <Link to={`/leads/${l.id}`} className="truncate text-brand-600 hover:underline">
                    {l.company_name}
                  </Link>
                  <PriorityBadge priority={l.lead_priority} />
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>
    </Card>
  );
}
