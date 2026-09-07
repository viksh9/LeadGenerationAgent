import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { X } from 'lucide-react';
import { PriorityBadge } from '@/components/ui/Badge';
import { DecisionMakerTypeBadge } from '@/components/contacts/badges';
import { RelevanceScore } from '@/components/contacts/RelevanceScore';
import { ContactEvidence } from '@/components/contacts/ContactEvidence';
import { UrgencyBadge } from '@/components/opportunities/badges';
import { StaffingNeedBadge } from '@/components/opportunities/badges';
import { opportunityLabel } from '@/services/contacts';
import type { ContactRecommendation } from '@/types/contact';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-800 dark:text-slate-200">{children}</dd>
    </div>
  );
}

/** Detail drawer keyed to a recommendation (no stable backend contact id). */
export function ContactRecommendationDetails({
  contact: c,
  onClose,
}: {
  contact: ContactRecommendation | null;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!c) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [c, onClose]);

  if (!c) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`${c.role} recommendation for ${c.company}`}
        className="h-full w-full max-w-md overflow-y-auto bg-white dark:bg-slate-900 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-slate-100 dark:border-slate-800 p-4">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-slate-900 dark:text-slate-100">{c.role}</h2>
            <p className="text-xs text-slate-400 dark:text-slate-500">
              {c.company}
              {c.industry ? ` · ${c.industry}` : ''}
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="rounded-md p-1 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-700 dark:hover:text-slate-300"
            onClick={onClose}
            aria-label="Close recommendation details"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <div className="space-y-4 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <DecisionMakerTypeBadge type={c.decisionMakerType} />
            <StaffingNeedBadge need={c.staffingNeed} />
            <UrgencyBadge urgency={c.urgency} reason={c.urgencyReason} />
            <PriorityBadge priority={c.priority} />
          </div>

          <Row label="Relevance">
            <RelevanceScore relevance={c.relevance} />
          </Row>

          <Row label="Recommendation confidence">{c.confidence}</Row>

          <Row label="Verified person">
            {c.personName ? (
              <span>{c.personName}</span>
            ) : (
              <span className="text-slate-500 dark:text-slate-400">Person not identified yet</span>
            )}
          </Row>

          <Row label="Why this role">{c.reason ?? 'Not available'}</Row>

          <Row label="Opportunity">
            <span>{opportunityLabel(c)}</span>
            {c.opportunitySummary && (
              <span className="mt-0.5 block text-slate-600 dark:text-slate-300">{c.opportunitySummary}</span>
            )}
            <span className="mt-0.5 block text-xs text-slate-400 dark:text-slate-500">
              Lead score: {Math.round(c.leadScore)} ·{' '}
              {c.estimatedHiring != null ? `${c.estimatedHiring} engineers` : 'Team size not available'}
            </span>
          </Row>

          <Row label="Recommended action">{c.recommendedAction ?? 'Not available'}</Row>

          <ContactEvidence contact={c} />

          <div className="flex gap-2">
            <Link to={`/leads/${c.leadId}`} className="btn-primary flex-1 justify-center">
              View lead
            </Link>
            <Link
              to={`/companies/${encodeURIComponent(c.company)}`}
              className="btn-secondary flex-1 justify-center"
            >
              View company
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
