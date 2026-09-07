import { PriorityBadge } from '@/components/ui/Badge';
import { DecisionMakerTypeBadge } from '@/components/contacts/badges';
import { RelevanceScore } from '@/components/contacts/RelevanceScore';
import { opportunityLabel } from '@/services/contacts';
import type { ContactRecommendation } from '@/types/contact';

/** Mobile/responsive card for a role recommendation. */
export function ContactCard({
  contact: c,
  onOpen,
}: {
  contact: ContactRecommendation;
  onOpen: (contact: ContactRecommendation) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(c)}
      className="card card-pad w-full text-left hover:border-slate-300 dark:hover:border-slate-700"
      aria-label={`View ${c.role} recommendation for ${c.company}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium text-slate-900 dark:text-slate-100">{c.company}</p>
          <p className="text-xs text-slate-400 dark:text-slate-500">{c.industry ?? '—'}</p>
        </div>
        <PriorityBadge priority={c.priority} />
      </div>

      <p className="mt-2 font-medium text-slate-800 dark:text-slate-200">{c.role}</p>
      <p className="text-xs text-slate-400 dark:text-slate-500">Person not identified yet</p>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <DecisionMakerTypeBadge type={c.decisionMakerType} />
        <span className="text-xs text-slate-500 dark:text-slate-400">{opportunityLabel(c)}</span>
      </div>

      <div className="mt-3">
        <RelevanceScore relevance={c.relevance} />
      </div>
    </button>
  );
}
