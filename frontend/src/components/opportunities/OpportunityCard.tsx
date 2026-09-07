import { PriorityBadge } from '@/components/ui/Badge';
import { OpportunityTypeBadge, StaffingNeedBadge, UrgencyBadge } from '@/components/opportunities/badges';
import { TechTags } from '@/components/opportunities/TechTags';
import type { Opportunity } from '@/types/opportunity';

/** Mobile/responsive card representation of an opportunity. */
export function OpportunityCard({
  opportunity: o,
  onOpen,
}: {
  opportunity: Opportunity;
  onOpen: (opportunity: Opportunity) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(o)}
      className="card card-pad w-full text-left hover:border-slate-300 dark:hover:border-slate-700"
      aria-label={`View opportunity for ${o.company}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium text-slate-900 dark:text-slate-100">{o.company}</p>
          <p className="text-xs text-slate-400 dark:text-slate-500">{o.industry ?? '—'}</p>
        </div>
        <div className="text-right">
          <p className="text-lg font-semibold tabular-nums text-slate-900 dark:text-slate-100">{Math.round(o.score)}</p>
          <PriorityBadge priority={o.priority} />
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <OpportunityTypeBadge type={o.opportunityType} />
        <StaffingNeedBadge need={o.staffingNeed} />
        <UrgencyBadge urgency={o.urgency} reason={o.urgencyReason} />
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div>
          <dt className="text-slate-400 dark:text-slate-500">Estimated team</dt>
          <dd className="text-slate-700 dark:text-slate-300">
            {o.estimatedHiring != null ? `${o.estimatedHiring} engineers` : 'Not available'}
          </dd>
        </div>
        <div>
          <dt className="text-slate-400 dark:text-slate-500">Status</dt>
          <dd className="text-slate-700 dark:text-slate-300">{o.status}</dd>
        </div>
      </dl>

      <div className="mt-3">
        <TechTags technologies={o.technologies} />
      </div>

      {o.recommendedAction && (
        <p className="mt-3 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">{o.recommendedAction}</p>
      )}
    </button>
  );
}
