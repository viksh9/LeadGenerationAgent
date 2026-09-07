import { Link } from 'react-router-dom';
import { Card, CardTitle } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/States';
import { formatScore, timeAgo } from '@/utils/format';
import type { Lead } from '@/types/lead';

export function RecentSignals({ leads }: { leads: Lead[] }) {
  return (
    <Card padded={false}>
      <div className="px-5 py-4">
        <CardTitle>Recent Signals</CardTitle>
      </div>
      {leads.length === 0 ? (
        <EmptyState title="No signals yet" description="Newly detected buying signals appear here." />
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {leads.map((lead) => (
            <li key={lead.id}>
              <Link
                to={`/leads/${lead.id}`}
                className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">{lead.company_name}</p>
                  <div className="mt-1 flex items-center gap-2">
                    {lead.signal_type && <Badge>{lead.signal_type}</Badge>}
                    <span className="truncate text-xs text-slate-500 dark:text-slate-400">
                      {lead.signal_title ?? '—'}
                    </span>
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-xs text-slate-400 dark:text-slate-500">{timeAgo(lead.signal_date)}</p>
                  <p className="text-sm font-semibold tabular-nums text-slate-700 dark:text-slate-300">
                    {formatScore(lead.lead_score)}
                  </p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
