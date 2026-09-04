import { Target } from 'lucide-react';
import { PriorityBadge } from '@/components/ui/Badge';
import { CopyButton } from '@/components/leads/detail/primitives';
import type { Lead } from '@/types/lead';

/**
 * The single most important "what to do next" card. Uses only persisted
 * recommendation fields — no invented deadlines or POC names.
 */
export function RecommendationCard({ lead }: { lead: Lead }) {
  const poc = [lead.poc_name, lead.poc_title].filter(Boolean).join(' · ');
  return (
    <section className="card card-pad" aria-label="Recommended action">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
        <Target className="h-4 w-4 text-brand-600" aria-hidden="true" />
        Recommended next step
      </h3>

      {lead.recommended_action ? (
        <>
          <p className="mt-2 text-sm leading-relaxed text-slate-700">{lead.recommended_action}</p>
          <div className="mt-2 flex justify-end">
            <CopyButton text={lead.recommended_action} label="Copy recommended action" />
          </div>
        </>
      ) : (
        <p className="mt-2 text-sm text-slate-400">Not available</p>
      )}

      <dl className="mt-3 space-y-2 border-t border-slate-100 pt-3">
        <div className="flex items-center justify-between">
          <dt className="text-xs uppercase tracking-wide text-slate-400">Priority</dt>
          <dd>
            <PriorityBadge priority={lead.lead_priority} />
          </dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt className="text-xs uppercase tracking-wide text-slate-400">Recommended POC</dt>
          <dd className="truncate text-right text-sm text-slate-700">{poc || 'Not available'}</dd>
        </div>
      </dl>
    </section>
  );
}
