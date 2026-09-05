import type { LeadStatistics } from '@/types/analytics';

function Kpi({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="card card-pad">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

export function KpiStats({ stats }: { stats: LeadStatistics }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <Kpi label="Total leads" value={stats.totalLeads.toLocaleString()} />
      <Kpi label="Hot leads" value={stats.hotLeads} />
      <Kpi label="Qualified" value={stats.qualifiedOpportunities} hint="Current status" />
      <Kpi label="Avg score" value={`${stats.averageScore} / 100`} />
      <Kpi label="High staffing" value={stats.highStaffing} />
      <Kpi label="Ready for outreach" value={stats.readyForOutreach} />
    </div>
  );
}
