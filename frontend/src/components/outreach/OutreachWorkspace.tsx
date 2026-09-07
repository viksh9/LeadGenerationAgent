import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, RefreshCw, ShieldCheck } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/States';
import { cn } from '@/utils/cn';
import { formatDateTime } from '@/utils/format';
import {
  useApproveDraft,
  useCancelDraft,
  useDrafts,
  useEditDraft,
  useProviderStatus,
  useSendDraft,
} from '@/hooks/useOutreachApi';
import { useFollowUps, useSetFollowUpStatus } from '@/hooks/useCrm';
import { draftStatusDisplay } from '@/services/outreachApi';
import type { OutreachDraft, ProviderStatus } from '@/services/outreachApi';
import { followUpStatusDisplay, followUpTypeLabel } from '@/services/crm';
import type { FollowUpTask } from '@/services/crm';

type WorkspaceTab = 'review' | 'ready' | 'sent' | 'replies' | 'followups';

const TABS: { id: WorkspaceTab; label: string }[] = [
  { id: 'review', label: 'Needs Review' },
  { id: 'ready', label: 'Ready to Send' },
  { id: 'sent', label: 'Sent' },
  { id: 'replies', label: 'Replies' },
  { id: 'followups', label: 'Follow-ups' },
];

function providerNotConfigured(provider?: ProviderStatus): boolean {
  return provider?.email_status === 'NOT_CONFIGURED';
}

function ProviderBanner({ provider }: { provider?: ProviderStatus }) {
  const notConfigured = providerNotConfigured(provider);
  const tone = notConfigured
    ? 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300'
    : 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300';
  const Icon = notConfigured ? AlertTriangle : ShieldCheck;
  return (
    <div className={cn('flex items-start gap-3 rounded-lg border p-3 text-sm', tone)}>
      <Icon className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
      <div className="min-w-0">
        <p className="font-medium">
          Email provider:{' '}
          {provider?.email_provider ?? 'None'} — {provider?.email_status ?? 'Unknown'}
        </p>
        {provider?.email_from && <p className="text-xs opacity-90">From: {provider.email_from}</p>}
        {notConfigured && (
          <p className="text-xs opacity-90">
            Email provider not configured — drafts can be approved but not sent.
          </p>
        )}
        {provider?.note && <p className="mt-0.5 text-xs opacity-80">{provider.note}</p>}
      </div>
    </div>
  );
}

function DraftCard({
  draft,
  provider,
}: {
  draft: OutreachDraft;
  provider?: ProviderStatus;
}) {
  const approve = useApproveDraft();
  const cancel = useCancelDraft();
  const send = useSendDraft();
  const edit = useEditDraft();
  const [editing, setEditing] = useState(false);
  const [subject, setSubject] = useState(draft.subject ?? '');
  const [message, setMessage] = useState(draft.message ?? '');

  const status = draftStatusDisplay(draft.status);
  const isReviewable = draft.status === 'DRAFT' || draft.status === 'READY_FOR_REVIEW';
  const notConfigured = providerNotConfigured(provider);

  const canApprove = isReviewable && draft.grounding_ok;
  const canSend = draft.status === 'APPROVED' && !notConfigured;
  const canCancel = isReviewable || draft.status === 'APPROVED';
  const busy = approve.isPending || cancel.isPending || send.isPending || edit.isPending;

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            {draft.lead_id ? (
              <Link to={`/leads/${draft.lead_id}`} className="hover:underline">
                Lead #{draft.lead_id}
              </Link>
            ) : (
              'Outreach draft'
            )}
          </p>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            {draft.channel}
            {draft.target_role ? ` · ${draft.target_role}` : ''}
            {` · ${draft.evidence_ids.length} evidence`}
            {` · confidence ${draft.confidence}`}
          </p>
        </div>
        <span className={cn('badge shrink-0', status.className)}>{status.label}</span>
      </div>

      {!draft.grounding_ok && (
        <p className="mt-3 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          Not evidence-grounded — add evidence before approving
        </p>
      )}

      {editing ? (
        <div className="mt-3 space-y-3">
          <Input
            label="Subject"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
          />
          <div>
            <label className="label" htmlFor={`draft-message-${draft.id}`}>
              Message
            </label>
            <textarea
              id={`draft-message-${draft.id}`}
              className="input min-h-[120px]"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-primary text-sm"
              disabled={edit.isPending}
              onClick={() =>
                edit.mutate(
                  { id: draft.id, body: { subject, message } },
                  { onSuccess: () => setEditing(false) },
                )
              }
            >
              Save
            </button>
            <button
              type="button"
              className="btn-secondary text-sm"
              disabled={edit.isPending}
              onClick={() => {
                setSubject(draft.subject ?? '');
                setMessage(draft.message ?? '');
                setEditing(false);
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <>
          {draft.subject && (
            <p className="mt-3 text-sm font-medium text-slate-800 dark:text-slate-200">
              {draft.subject}
            </p>
          )}
          <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-sm text-slate-600 dark:text-slate-300">
            {draft.message || 'No message content yet.'}
          </p>
        </>
      )}

      {draft.recipient_email && (
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">To: {draft.recipient_email}</p>
      )}
      {draft.status === 'SENT' && draft.sent_at && (
        <p className="mt-2 text-xs text-emerald-700 dark:text-emerald-400">
          Sent {formatDateTime(draft.sent_at)}
          {draft.provider ? ` via ${draft.provider}` : ''}
        </p>
      )}
      {draft.status === 'FAILED' && draft.error && (
        <p className="mt-2 text-xs text-rose-600 dark:text-rose-400">Send failed: {draft.error}</p>
      )}

      {!editing && draft.status !== 'SENT' && draft.status !== 'CANCELLED' && (
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            className="btn-primary text-sm"
            disabled={!canApprove || busy}
            title={
              !draft.grounding_ok
                ? 'Add evidence before approving'
                : !isReviewable
                  ? 'Only draft or ready-for-review items can be approved'
                  : undefined
            }
            onClick={() => approve.mutate(draft.id)}
          >
            Approve
          </button>
          <button
            type="button"
            className="btn-secondary text-sm"
            disabled={!canSend || busy}
            title={
              notConfigured
                ? 'Email provider not configured — drafts can be approved but not sent.'
                : draft.status !== 'APPROVED'
                  ? 'Only approved drafts can be sent'
                  : undefined
            }
            onClick={() => send.mutate(draft.id)}
          >
            Send
          </button>
          {isReviewable && (
            <button
              type="button"
              className="btn-secondary text-sm"
              disabled={busy}
              onClick={() => setEditing(true)}
            >
              Edit
            </button>
          )}
          {canCancel && (
            <button
              type="button"
              className="btn-ghost text-sm"
              disabled={busy}
              onClick={() => cancel.mutate(draft.id)}
            >
              Cancel
            </button>
          )}
        </div>
      )}
    </Card>
  );
}

function DraftGrid({
  drafts,
  provider,
  emptyText,
}: {
  drafts: OutreachDraft[];
  provider?: ProviderStatus;
  emptyText: string;
}) {
  if (drafts.length === 0) {
    return (
      <Card>
        <EmptyState title={emptyText} />
      </Card>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      {drafts.map((d) => (
        <DraftCard key={d.id} draft={d} provider={provider} />
      ))}
    </div>
  );
}

function FollowUpsPanel() {
  const followUps = useFollowUps();
  const setStatus = useSetFollowUpStatus();

  if (followUps.isLoading) return <LoadingState message="Loading follow-ups…" />;
  if (followUps.isError)
    return (
      <ErrorState message="Unable to load follow-ups." onRetry={() => followUps.refetch()} />
    );

  const items = followUps.data?.items ?? [];
  if (items.length === 0) {
    return (
      <Card>
        <EmptyState title="No sales activity recorded." />
      </Card>
    );
  }

  return (
    <div className="space-y-2">
      {items.map((task: FollowUpTask) => {
        const st = followUpStatusDisplay(task.status);
        return (
          <Card key={task.id}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{task.title}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {followUpTypeLabel(task.task_type)}
                  {task.due_at ? ` · due ${formatDateTime(task.due_at)}` : ''}
                  {task.lead_id ? ` · lead #${task.lead_id}` : ''}
                </p>
                {task.reason && (
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{task.reason}</p>
                )}
              </div>
              <span className={cn('badge shrink-0', st.className)}>{st.label}</span>
            </div>
            {task.status !== 'COMPLETED' && task.status !== 'CANCELLED' && (
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  className="btn-secondary text-sm"
                  disabled={setStatus.isPending}
                  onClick={() => setStatus.mutate({ id: task.id, status: 'COMPLETED' })}
                >
                  Mark complete
                </button>
                <button
                  type="button"
                  className="btn-ghost text-sm"
                  disabled={setStatus.isPending}
                  onClick={() => setStatus.mutate({ id: task.id, status: 'CANCELLED' })}
                >
                  Dismiss
                </button>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}

/**
 * The real-backend outreach workspace: live drafts (generate → review → approve
 * → send), provider status, and follow-up tasks. Distinct from the derived
 * "prep" view — everything here is persisted by the backend, and no message is
 * ever shown as sent unless the backend reports status === "SENT".
 */
export function OutreachWorkspace() {
  const [tab, setTab] = useState<WorkspaceTab>('review');
  const draftsQuery = useDrafts();
  const providerQuery = useProviderStatus();
  const provider = providerQuery.data;

  const drafts = draftsQuery.data?.items ?? [];
  const review = drafts.filter((d) => d.status === 'DRAFT' || d.status === 'READY_FOR_REVIEW');
  const ready = drafts.filter((d) => d.status === 'APPROVED');
  const sent = drafts.filter((d) => d.status === 'SENT');

  return (
    <div className="space-y-4">
      {providerQuery.isLoading ? (
        <Card>
          <p className="text-sm text-slate-500 dark:text-slate-400">Checking email provider…</p>
        </Card>
      ) : providerQuery.isError ? (
        <ErrorState
          message="Unable to load email provider status."
          onRetry={() => providerQuery.refetch()}
        />
      ) : (
        <ProviderBanner provider={provider} />
      )}

      <div className="flex items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-800">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={tab === t.id}
              className={cn(
                'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                tab === t.id
                  ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-900 dark:text-slate-100'
                  : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200',
              )}
              onClick={() => setTab(t.id)}
            >
              {t.label}
              {t.id === 'review' && review.length > 0 ? ` (${review.length})` : ''}
              {t.id === 'ready' && ready.length > 0 ? ` (${ready.length})` : ''}
              {t.id === 'sent' && sent.length > 0 ? ` (${sent.length})` : ''}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="btn-ghost text-sm"
          onClick={() => draftsQuery.refetch()}
          disabled={draftsQuery.isFetching}
          aria-label="Refresh drafts"
        >
          <RefreshCw
            className={draftsQuery.isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
            aria-hidden="true"
          />
          Refresh
        </button>
      </div>

      {tab === 'followups' ? (
        <FollowUpsPanel />
      ) : tab === 'replies' ? (
        <Card>
          <EmptyState
            title="No real CRM activity available."
            description="Inbound replies are recorded on each lead's activity timeline. Open a lead to review its replies."
          />
        </Card>
      ) : draftsQuery.isLoading ? (
        <LoadingState message="Loading outreach drafts…" />
      ) : draftsQuery.isError ? (
        <ErrorState
          message="Unable to load outreach drafts."
          onRetry={() => draftsQuery.refetch()}
        />
      ) : tab === 'review' ? (
        <DraftGrid drafts={review} provider={provider} emptyText="No outreach-ready real leads." />
      ) : tab === 'ready' ? (
        <DraftGrid drafts={ready} provider={provider} emptyText="No outreach-ready real leads." />
      ) : (
        <DraftGrid drafts={sent} provider={provider} emptyText="No sales activity recorded." />
      )}
    </div>
  );
}
