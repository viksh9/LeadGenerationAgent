import { Flame } from 'lucide-react';
import { Card, CardTitle } from '@/components/ui/Card';
import { PriorityBadge } from '@/components/ui/Badge';
import { OpportunityTypeBadge, StaffingNeedBadge } from '@/components/opportunities/badges';
import type { Opportunity } from '@/types/opportunity';

/** Top 5 opportunities by score. Each item opens the detail drawer. */
export function TopOpportunities({
  opportunities,
  onOpen,
}: {
  opportunities: Opportunity[];
  onOpen: (opportunity: Opportunity) => void;
}) {
  const top = [...opportunities].sort((a, b) => b.score - a.score).slice(0, 5);
  if (top.length === 0) return null;

  return (
    <Card>
      <CardTitle>Top opportunities</CardTitle>
      <ul className="mt-3 divide-y divide-slate-100">
        {top.map((o) => (
          <li key={o.leadId}>
            <button
              type="button"
              onClick={() => onOpen(o)}
              className="flex w-full items-center gap-3 py-2.5 text-left hover:bg-slate-50"
              aria-label={`View top opportunity for ${o.company}`}
            >
              <Flame className="h-4 w-4 shrink-0 text-rose-500" aria-hidden="true" />
              <span className="w-8 shrink-0 text-lg font-semibold tabular-nums text-slate-900">
                {Math.round(o.score)}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-slate-800">{o.company}</span>
                <span className="mt-1 flex flex-wrap items-center gap-1.5">
                  <OpportunityTypeBadge type={o.opportunityType} />
                  <StaffingNeedBadge need={o.staffingNeed} />
                </span>
                {o.recommendedAction && (
                  <span className="mt-1 block truncate text-xs text-slate-500">{o.recommendedAction}</span>
                )}
              </span>
              <PriorityBadge priority={o.priority} />
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}
