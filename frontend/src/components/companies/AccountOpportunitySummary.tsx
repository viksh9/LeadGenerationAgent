import { PriorityBadge } from '@/components/ui/Badge';
import { DetailCard } from '@/components/leads/detail/DetailCard';
import type { CompanyIntelligence } from '@/types/company';

function staffingNeed(estimatedHiring: number): 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN' {
  if (estimatedHiring <= 0) return 'UNKNOWN';
  if (estimatedHiring >= 25) return 'HIGH';
  if (estimatedHiring >= 10) return 'MEDIUM';
  return 'LOW';
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3">
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <div className="mt-1 text-sm font-semibold text-slate-900">{value}</div>
    </div>
  );
}

/**
 * Account-level opportunity summary derived from the strongest related lead and
 * simple aggregates. Staffing need is a band of the summed estimated hiring — a
 * presentation of existing data, not a new account score.
 */
export function AccountOpportunitySummary({ company }: { company: CompanyIntelligence }) {
  const need = staffingNeed(company.hiring.estimatedHiring);
  return (
    <DetailCard title="Account opportunity summary">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Metric label="Priority" value={<PriorityBadge priority={company.topPriority} />} />
        <Metric label="Highest score" value={`${Math.round(company.bestScore)} / 100`} />
        <Metric label="Open opportunities" value={company.metrics.opportunityCount} />
        <Metric label="Technology hiring" value={company.hiring.estimatedHiring || '—'} />
        <Metric label="Recent signals" value={company.metrics.totalSignals} />
        <Metric label="Potential staffing need" value={need} />
      </div>
    </DetailCard>
  );
}
