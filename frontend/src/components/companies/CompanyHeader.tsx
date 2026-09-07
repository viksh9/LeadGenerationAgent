import { PriorityBadge } from '@/components/ui/Badge';
import { ScoreIndicator } from '@/components/common/ScoreIndicator';
import type { CompanyIntelligence } from '@/types/company';

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="text-right">
      <p className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</p>
      <p className="text-lg font-semibold tabular-nums text-slate-900 dark:text-slate-100">{value}</p>
    </div>
  );
}

/** Account identity + headline metrics band. */
export function CompanyHeader({ company }: { company: CompanyIntelligence }) {
  return (
    <section className="card card-pad" aria-label="Account summary">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <PriorityBadge priority={company.topPriority} />
            <span className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
              Account opportunity
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
            {company.metrics.totalSignals} signal{company.metrics.totalSignals === 1 ? '' : 's'} ·{' '}
            {company.metrics.opportunityCount} opportunit
            {company.metrics.opportunityCount === 1 ? 'y' : 'ies'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-6">
          <Stat label="Open leads" value={company.leadCount} />
          <Stat label="Signals" value={company.metrics.totalSignals} />
          <div className="text-right">
            <p className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Best score</p>
            <div className="mt-1 flex justify-end">
              <ScoreIndicator score={company.bestScore} />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
