import type { OpportunitySummary as Summary } from '@/types/opportunity';

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div className="card card-pad">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</p>
    </div>
  );
}

/** Opportunity funnel — all counts derived from the current dataset. */
export function OpportunitySummary({ summary }: { summary: Summary }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <Kpi label="Total" value={summary.total} />
      <Kpi label="Hot" value={summary.hot} />
      <Kpi label="High staffing" value={summary.highStaffing} />
      <Kpi label="High urgency" value={summary.highUrgency} />
      <Kpi label="Qualified" value={summary.qualified} />
    </div>
  );
}
