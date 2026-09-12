import { useState } from 'react';
import { CheckCircle2, FileSearch, Mail, XCircle } from 'lucide-react';

import { DetailCard } from '@/components/leads/detail/DetailCard';
import { EvidenceDrawer } from '@/components/leads/detail/EvidenceDrawer';
import { useTransitionLead } from '@/hooks/useCrm';
import { useGenerateDraft } from '@/hooks/useOutreachApi';

/**
 * Lead action bar (§21). Drives the CONTROLLED lifecycle via the validated transition
 * endpoint (POST /leads/{id}/transition) — not the raw status PUT — so illegal
 * transitions are rejected server-side with an honest error. Disqualifying requires a
 * stored reason (§14). Also offers Prepare Outreach (grounded draft) and View Evidence.
 * Every action maps to a real backend operation; nothing is faked.
 */
const LIFECYCLE = ['NEW', 'RESEARCHED', 'OUTREACH_READY', 'CONTACTED', 'REPLIED', 'MEETING',
  'QUALIFIED', 'PROPOSAL', 'WON', 'LOST', 'NURTURE'] as const;

const DISQUALIFY_REASONS = ['Not relevant', 'Duplicate', 'No current opportunity', 'Wrong geography',
  'Wrong technology', 'Invalid signal', 'Poor data quality', 'Other'] as const;

export function LeadActionBar({ leadId, status }: { leadId: number; status: string }) {
  const transition = useTransitionLead(leadId);
  const draft = useGenerateDraft();
  const [drawer, setDrawer] = useState(false);
  const [disqualifyOpen, setDisqualifyOpen] = useState(false);
  const [reason, setReason] = useState<string>(DISQUALIFY_REASONS[0]);
  const [note, setNote] = useState('');

  const go = (newStatus: string) => transition.mutate({ new_status: newStatus });

  const confirmDisqualify = () => {
    const full = note.trim() ? `${reason} — ${note.trim()}` : reason;
    transition.mutate(
      { new_status: 'DISQUALIFIED', reason: full },
      { onSuccess: () => { setDisqualifyOpen(false); setNote(''); } },
    );
  };

  return (
    <>
      <DetailCard title="Actions">
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn-secondary text-sm" disabled={transition.isPending || status === 'RESEARCHED'}
            onClick={() => go('RESEARCHED')}>
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> Mark Reviewed
          </button>
          <button type="button" className="btn-secondary text-sm" disabled={transition.isPending || status === 'QUALIFIED'}
            onClick={() => go('QUALIFIED')}>
            Qualify
          </button>
          <button type="button" className="btn-secondary text-sm" disabled={draft.isPending}
            onClick={() => draft.mutate({ lead_id: leadId })}>
            <Mail className="h-4 w-4" aria-hidden="true" /> {draft.isPending ? 'Preparing…' : 'Prepare Outreach'}
          </button>
          <button type="button" className="btn-ghost text-sm" onClick={() => setDrawer(true)}>
            <FileSearch className="h-4 w-4" aria-hidden="true" /> View Evidence
          </button>

          <label className="ml-auto flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
            <span className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Change status</span>
            <select
              className="select text-sm"
              value={LIFECYCLE.includes(status as never) ? status : ''}
              disabled={transition.isPending}
              onChange={(e) => e.target.value && go(e.target.value)}
              aria-label="Change lead status"
            >
              {!LIFECYCLE.includes(status as never) && <option value="">{status}</option>}
              {LIFECYCLE.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
            </select>
          </label>

          <button type="button" className="btn-danger text-sm" disabled={transition.isPending || status === 'DISQUALIFIED'}
            onClick={() => setDisqualifyOpen(true)}>
            <XCircle className="h-4 w-4" aria-hidden="true" /> Disqualify
          </button>
        </div>
      </DetailCard>

      {disqualifyOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
          onClick={() => !transition.isPending && setDisqualifyOpen(false)}>
          <div role="dialog" aria-modal="true" aria-label="Disqualify lead"
            className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-700 dark:bg-slate-900"
            onClick={(e) => e.stopPropagation()}>
            <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">Disqualify lead</h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
              A reason is required. The underlying evidence is kept — only the sales status changes.
            </p>
            <label className="label mt-4 block">Reason</label>
            <select className="select w-full" value={reason} onChange={(e) => setReason(e.target.value)}>
              {DISQUALIFY_REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <label className="label mt-3 block">Note (optional)</label>
            <textarea className="input w-full" rows={2} value={note} onChange={(e) => setNote(e.target.value)}
              placeholder="Add context (optional)" />
            <div className="mt-4 flex justify-end gap-2">
              <button type="button" className="btn-ghost text-sm" disabled={transition.isPending}
                onClick={() => setDisqualifyOpen(false)}>Cancel</button>
              <button type="button" className="btn-danger text-sm" disabled={transition.isPending}
                onClick={confirmDisqualify}>{transition.isPending ? 'Saving…' : 'Disqualify'}</button>
            </div>
          </div>
        </div>
      )}

      <EvidenceDrawer leadId={leadId} open={drawer} onClose={() => setDrawer(false)} />
    </>
  );
}
