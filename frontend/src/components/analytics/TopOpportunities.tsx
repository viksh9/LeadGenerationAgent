import { useNavigate } from 'react-router-dom';
import { Card, CardTitle } from '@/components/ui/Card';
import { PriorityBadge } from '@/components/ui/Badge';
import { StaffingNeedBadge, UrgencyBadge } from '@/components/opportunities/badges';
import { OPPORTUNITY_TYPE_LABELS } from '@/services/opportunities';
import type { TopOpportunityRow } from '@/types/analytics';

/** Highest-scoring opportunities; each navigates to the related lead (§16). */
export function TopOpportunities({ rows }: { rows: TopOpportunityRow[] }) {
  const navigate = useNavigate();
  return (
    <Card>
      <CardTitle>Top opportunities</CardTitle>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-slate-400">Not enough data yet</p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-100">
          {rows.map((o) => (
            <li key={o.leadId}>
              <button
                type="button"
                onClick={() => navigate(`/leads/${o.leadId}`)}
                className="flex w-full items-center gap-3 py-2 text-left hover:bg-slate-50"
                aria-label={`View lead ${o.leadId} for ${o.company}`}
              >
                <span className="w-8 shrink-0 text-sm font-semibold tabular-nums text-slate-900">
                  {Math.round(o.score)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-slate-800">{o.company}</span>
                  <span className="mt-1 flex flex-wrap items-center gap-1.5">
                    <span className="text-xs text-slate-500">{OPPORTUNITY_TYPE_LABELS[o.opportunityType]}</span>
                    <StaffingNeedBadge need={o.staffingNeed} />
                    <UrgencyBadge urgency={o.urgency} />
                  </span>
                </span>
                <PriorityBadge priority={o.priority} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
