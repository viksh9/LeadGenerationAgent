import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Mail } from 'lucide-react';
import { DetailCard, Field } from '@/components/leads/detail/DetailCard';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/States';
import { cn } from '@/utils/cn';
import { formatDateTime } from '@/utils/format';
import { useLeadTimeline, useNextBestAction, useStatusHistory } from '@/hooks/useCrm';
import { useGenerateDraft } from '@/hooks/useOutreachApi';

const SYSTEM_BADGE = 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';
const HUMAN_BADGE = 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300';

/** Merged system-event + human-activity timeline for a lead. */
export function LeadTimelineCard({ leadId }: { leadId: number }) {
  const timeline = useLeadTimeline(leadId);

  return (
    <DetailCard title="Activity timeline">
      {timeline.isLoading ? (
        <LoadingState message="Loading the activity timeline…" />
      ) : timeline.isError ? (
        <ErrorState message="Unable to load the activity timeline." onRetry={() => timeline.refetch()} />
      ) : (timeline.data?.items ?? []).length === 0 ? (
        <EmptyState title="No real CRM activity available." />
      ) : (
        <ol className="space-y-3">
          {timeline.data!.items.map((item, i) => {
            const isSystem = item.kind === 'SYSTEM_EVENT';
            return (
              <li
                key={`${item.occurred_at}-${i}`}
                className="border-l-2 border-slate-200 pl-3 dark:border-slate-700"
              >
                <div className="flex items-center gap-2">
                  <span className={cn('badge', isSystem ? SYSTEM_BADGE : HUMAN_BADGE)}>
                    {isSystem ? 'System event' : 'Human activity'}
                  </span>
                  <span className="text-xs text-slate-400 dark:text-slate-500">
                    {formatDateTime(item.occurred_at)}
                  </span>
                </div>
                <p className="mt-1 text-sm font-medium text-slate-800 dark:text-slate-200">
                  {item.title}
                </p>
                {item.detail && (
                  <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">{item.detail}</p>
                )}
                {item.source && (
                  <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">
                    Source: {item.source}
                  </p>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </DetailCard>
  );
}

/** The lead's status-transition history. */
export function LeadStatusHistoryCard({ leadId }: { leadId: number }) {
  const history = useStatusHistory(leadId);

  return (
    <DetailCard title="Status history">
      {history.isLoading ? (
        <LoadingState message="Loading status history…" />
      ) : history.isError ? (
        <ErrorState message="Unable to load status history." onRetry={() => history.refetch()} />
      ) : (history.data ?? []).length === 0 ? (
        <EmptyState title="No sales activity recorded." />
      ) : (
        <ul className="space-y-3">
          {history.data!.map((h) => (
            <li key={h.id} className="text-sm">
              <p className="font-medium text-slate-800 dark:text-slate-200">
                {h.old_status ? `${h.old_status} → ${h.new_status}` : h.new_status}
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500">
                {formatDateTime(h.created_at)} · {h.changed_by}
              </p>
              {h.reason && (
                <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">{h.reason}</p>
              )}
            </li>
          ))}
        </ul>
      )}
    </DetailCard>
  );
}

/** Next best action + a "generate outreach draft" action for the lead. */
export function LeadNextActionCard({ leadId }: { leadId: number }) {
  const nextAction = useNextBestAction(leadId);
  const generate = useGenerateDraft();
  const [draftId, setDraftId] = useState<number | null>(null);

  return (
    <DetailCard title="Next best action">
      <div className="space-y-4">
        <Field label="Recommended next step">
          {nextAction.isLoading
            ? 'Loading…'
            : nextAction.isError
              ? 'Not available'
              : nextAction.data?.next_best_action || 'Not available'}
        </Field>

        <div>
          <button
            type="button"
            className="btn-primary text-sm"
            disabled={generate.isPending}
            onClick={() =>
              generate.mutate(
                { lead_id: leadId },
                { onSuccess: (draft) => setDraftId(draft.id) },
              )
            }
          >
            <Mail className="h-4 w-4" aria-hidden="true" />
            {generate.isPending ? 'Generating…' : 'Generate outreach draft'}
          </button>
          {draftId !== null && (
            <p className="mt-2 text-sm text-emerald-700 dark:text-emerald-400">
              Draft #{draftId} created.{' '}
              <Link to="/outreach" className="underline">
                Open in the outreach workspace
              </Link>
            </p>
          )}
        </div>
      </div>
    </DetailCard>
  );
}
