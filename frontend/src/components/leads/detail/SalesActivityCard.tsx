import { useState } from 'react';

import { DetailCard } from '@/components/leads/detail/DetailCard';
import { useCreateActivity, useCreateFollowUp, useLeadActivities } from '@/hooks/useCrm';
import { activityTypeDisplay, type ActivityType } from '@/services/crm';
import { formatDateTime } from '@/utils/format';

/**
 * User-created sales workflow (§9-§12): log a real activity (note/call/email/etc.),
 * add a follow-up, and see recorded activity. This is user-owned data — it never edits
 * source-backed intelligence, and no historical activity is fabricated (empty state is
 * honest). Activities are logged through the real CRM endpoints.
 */
const ACTIVITY_TYPES: { value: ActivityType; label: string }[] = [
  { value: 'NOTE', label: 'Note' },
  { value: 'CALL', label: 'Call' },
  { value: 'EMAIL', label: 'Email' },
  { value: 'LINKEDIN_MESSAGE', label: 'LinkedIn outreach' },
  { value: 'MEETING', label: 'Meeting' },
  { value: 'RESEARCH', label: 'Reviewed' },
];

export function SalesActivityCard({ leadId, companyId }: { leadId: number; companyId?: number | null }) {
  const activities = useLeadActivities(leadId);
  const logActivity = useCreateActivity();
  const createFollowUp = useCreateFollowUp(leadId);

  const [type, setType] = useState<ActivityType>('NOTE');
  const [note, setNote] = useState('');
  const [followTitle, setFollowTitle] = useState('');
  const [followDue, setFollowDue] = useState('');

  const submitActivity = () => {
    if (!note.trim()) return;
    logActivity.mutate(
      { activity_type: type, lead_id: leadId, company_id: companyId ?? undefined,
        subject: ACTIVITY_TYPES.find((t) => t.value === type)?.label, body_reference: note.trim() },
      { onSuccess: () => setNote('') },
    );
  };

  const submitFollowUp = () => {
    if (!followTitle.trim()) return;
    createFollowUp.mutate(
      { title: followTitle.trim(), due_at: followDue ? new Date(followDue).toISOString() : undefined },
      { onSuccess: () => { setFollowTitle(''); setFollowDue(''); } },
    );
  };

  const items = activities.data?.items ?? [];

  return (
    <DetailCard title="Sales activity">
      {/* Log activity */}
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Type</span>
          <select className="select text-sm" value={type} onChange={(e) => setType(e.target.value as ActivityType)}>
            {ACTIVITY_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </label>
        <label className="flex flex-1 flex-col gap-1" style={{ minWidth: 180 }}>
          <span className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Note</span>
          <input className="input text-sm" value={note} onChange={(e) => setNote(e.target.value)}
            placeholder="What happened? (real activity only)" />
        </label>
        <button type="button" className="btn-primary text-sm" disabled={logActivity.isPending || !note.trim()}
          onClick={submitActivity}>{logActivity.isPending ? 'Saving…' : 'Log activity'}</button>
      </div>

      {/* Add follow-up */}
      <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
        <label className="flex flex-1 flex-col gap-1" style={{ minWidth: 180 }}>
          <span className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Follow-up</span>
          <input className="input text-sm" value={followTitle} onChange={(e) => setFollowTitle(e.target.value)}
            placeholder="e.g. Call next Tuesday" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Due</span>
          <input type="date" className="input text-sm" value={followDue} onChange={(e) => setFollowDue(e.target.value)} />
        </label>
        <button type="button" className="btn-secondary text-sm" disabled={createFollowUp.isPending || !followTitle.trim()}
          onClick={submitFollowUp}>{createFollowUp.isPending ? 'Saving…' : 'Add follow-up'}</button>
      </div>

      {/* Recorded activity */}
      <div className="mt-4">
        {activities.isLoading ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">Loading activity…</p>
        ) : activities.isError ? (
          <p className="text-sm text-rose-600 dark:text-rose-400">Unable to load sales activity.</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">No sales activity recorded.</p>
        ) : (
          <ul className="space-y-2">
            {items.slice(0, 12).map((a) => {
              const disp = activityTypeDisplay(a.activity_type);
              return (
                <li key={a.id} className="flex items-start gap-2 text-sm">
                  <span className={`badge ${disp.className}`}>{disp.label}</span>
                  <div className="min-w-0">
                    <p className="break-words text-slate-800 dark:text-slate-200">{a.subject || a.body_reference || '—'}</p>
                    <p className="text-xs text-slate-400 dark:text-slate-500">
                      {formatDateTime(a.occurred_at)} · {a.is_system_event ? 'System' : a.created_by}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </DetailCard>
  );
}
