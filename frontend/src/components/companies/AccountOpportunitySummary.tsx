import { PriorityBadge } from '@/components/ui/Badge';
import { DetailCard } from '@/components/leads/detail/DetailCard';
import { useSignals } from '@/hooks/useSignals';
import { useTenders } from '@/hooks/useTenders';
import type { CompanyIntelligence } from '@/types/company';

function staffingNeed(estimatedHiring: number): 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN' {
  if (estimatedHiring <= 0) return 'UNKNOWN';
  if (estimatedHiring >= 25) return 'HIGH';
  if (estimatedHiring >= 10) return 'MEDIUM';
  return 'LOW';
}

function Metric({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40 p-3">
      <p className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</p>
      <div className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">{value}</div>
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

  // Real, evidence-referenced counts. Only what the backend actually returns.
  const { data: signals } = useSignals({ company: company.name, page_size: 1 });
  const { data: tenders } = useTenders({ organization: company.name, page_size: 1 });
  const signalCount = signals?.total ?? 0;
  const tenderCount = tenders?.total ?? 0;
  const openings = company.hiring.estimatedHiring;

  const parts: string[] = [];
  if (signalCount > 0) parts.push(`${signalCount} verified signal${signalCount === 1 ? '' : 's'}`);
  if (tenderCount > 0) parts.push(`${tenderCount} tender${tenderCount === 1 ? '' : 's'}`);
  if (openings > 0) parts.push(`${openings} estimated opening${openings === 1 ? '' : 's'}`);

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
      {parts.length > 0 && (
        <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
          <span className="font-medium text-slate-800 dark:text-slate-200">
            Why this is an opportunity:
          </span>{' '}
          {parts.join(', ')} for {company.name}.
        </p>
      )}
    </DetailCard>
  );
}
