import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { ExternalLink, X } from 'lucide-react';
import { PriorityBadge } from '@/components/ui/Badge';
import { OpportunityTypeBadge, StaffingNeedBadge, UrgencyBadge } from '@/components/opportunities/badges';
import { TechTags } from '@/components/opportunities/TechTags';
import { humanizeSignal } from '@/constants/leads';
import { formatDate } from '@/utils/format';
import type { Opportunity } from '@/types/opportunity';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-800">{children}</dd>
    </div>
  );
}

/** Side drawer with the opportunity's business case. Prefers linking to the lead. */
export function OpportunityDetailDrawer({
  opportunity: o,
  onClose,
}: {
  opportunity: Opportunity | null;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!o) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [o, onClose]);

  if (!o) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Opportunity for ${o.company}`}
        className="h-full w-full max-w-md overflow-y-auto bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-slate-100 p-4">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-slate-900">{o.company}</h2>
            <p className="text-xs text-slate-400">{o.industry ?? '—'}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            onClick={onClose}
            aria-label="Close opportunity details"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <div className="space-y-4 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <OpportunityTypeBadge type={o.opportunityType} />
            <StaffingNeedBadge need={o.staffingNeed} />
            <UrgencyBadge urgency={o.urgency} reason={o.urgencyReason} />
            <PriorityBadge priority={o.priority} />
          </div>

          <dl className="grid grid-cols-2 gap-3">
            <Row label="Score">
              <span className="text-lg font-semibold tabular-nums">{Math.round(o.score)} / 100</span>
            </Row>
            <Row label="Opportunity confidence">
              {o.confidence != null ? `${Math.round(o.confidence)}%` : 'Not available'}
            </Row>
            <Row label="Estimated team">
              {o.estimatedHiring != null ? `${o.estimatedHiring} engineers` : 'Not available'}
            </Row>
            <Row label="Status">{o.status}</Row>
          </dl>

          <Row label="Business reason">{o.businessReason ?? 'Not available'}</Row>

          <Row label="Technologies">
            <TechTags technologies={o.technologies} max={12} />
          </Row>

          <Row label="Target decision-maker">
            {o.pocRole || o.pocName ? (
              <span>
                {o.pocRole ?? 'Contact'}
                {o.pocName ? ` · ${o.pocName}` : ''}
              </span>
            ) : (
              'Not available'
            )}
            <p className="mt-0.5 text-xs text-slate-400">Secondary roles: not available</p>
          </Row>

          <Row label="Recommended action">{o.recommendedAction ?? 'Not available'}</Row>

          <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Evidence</p>
            <dl className="mt-2 space-y-2">
              <Row label="Signal">
                {o.signalType ? humanizeSignal(o.signalType) : 'Not available'}
                {o.signalTitle ? ` — ${o.signalTitle}` : ''}
              </Row>
              <Row label="Source">{o.sourceName ?? 'Not available'}</Row>
              <Row label="Signal date">{formatDate(o.signalDate)}</Row>
              <Row label="Confidence">
                {o.signalConfidence != null ? `${Math.round(o.signalConfidence)}%` : 'Not available'}
              </Row>
              {o.sourceUrl && (
                <a
                  href={o.sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-brand-600 hover:underline"
                >
                  Open source
                  <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                </a>
              )}
            </dl>
          </div>

          <Link to={`/leads/${o.leadId}`} className="btn-primary w-full justify-center">
            View full lead
          </Link>
        </div>
      </div>
    </div>
  );
}
