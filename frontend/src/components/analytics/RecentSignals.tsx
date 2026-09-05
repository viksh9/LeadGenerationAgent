import { useNavigate } from 'react-router-dom';
import { Card, CardTitle } from '@/components/ui/Card';
import { PriorityBadge } from '@/components/ui/Badge';
import { humanizeSignal } from '@/constants/leads';
import { formatDate } from '@/utils/format';
import type { RecentSignal } from '@/types/analytics';

/** Latest high-value signals; each navigates to the related lead (§15). */
export function RecentSignals({ signals }: { signals: RecentSignal[] }) {
  const navigate = useNavigate();
  return (
    <Card>
      <CardTitle>Recent high-value signals</CardTitle>
      {signals.length === 0 ? (
        <p className="mt-3 text-sm text-slate-400">Not enough data yet</p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-100">
          {signals.map((s) => (
            <li key={s.leadId}>
              <button
                type="button"
                onClick={() => navigate(`/leads/${s.leadId}`)}
                className="flex w-full items-center gap-3 py-2 text-left hover:bg-slate-50"
                aria-label={`View lead ${s.leadId} for ${s.company}`}
              >
                <span className="w-8 shrink-0 text-sm font-semibold tabular-nums text-slate-900">
                  {Math.round(s.score)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium text-slate-800">{s.company}</span>
                  <span className="text-xs text-slate-400">
                    {s.signalType ? humanizeSignal(s.signalType) : '—'} · {formatDate(s.date)}
                  </span>
                </span>
                <PriorityBadge priority={s.priority} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
