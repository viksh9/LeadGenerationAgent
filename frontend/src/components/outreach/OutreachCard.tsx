import { PriorityBadge } from '@/components/ui/Badge';
import { OutreachStatusBadge } from '@/components/outreach/badges';
import { OPPORTUNITY_TYPE_LABELS } from '@/services/opportunities';
import type { OutreachItem } from '@/types/outreach';

/** Mobile/responsive card for a queued outreach item. */
export function OutreachCard({
  item: o,
  onOpen,
}: {
  item: OutreachItem;
  onOpen: (item: OutreachItem) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(o)}
      className="card card-pad w-full text-left hover:border-slate-300"
      aria-label={`Review outreach for ${o.company}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium text-slate-900">{o.company}</p>
          <p className="text-xs text-slate-400">{o.role ?? o.industry ?? '—'}</p>
        </div>
        <div className="text-right">
          <p className="text-lg font-semibold tabular-nums text-slate-900">{Math.round(o.score)}</p>
          <PriorityBadge priority={o.priority} />
        </div>
      </div>
      <p className="mt-2 text-sm text-slate-600">{OPPORTUNITY_TYPE_LABELS[o.opportunityType]}</p>
      <div className="mt-2">
        <OutreachStatusBadge status={o.status} />
      </div>
    </button>
  );
}
