import type { OutreachSummary } from '@/types/outreach';

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div className="card card-pad">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">{value}</p>
    </div>
  );
}

export function OutreachSummaryCards({ summary }: { summary: OutreachSummary }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Kpi label="Ready for outreach" value={summary.ready} />
      <Kpi label="Needs review" value={summary.needsReview} />
      <Kpi label="Hot" value={summary.hot} />
      <Kpi label="In progress" value={summary.inProgress} />
    </div>
  );
}
