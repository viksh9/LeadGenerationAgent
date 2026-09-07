import { DetailCard } from '@/components/leads/detail/DetailCard';
import { Chips } from '@/components/leads/detail/primitives';
import type { CompanyIntelligence } from '@/types/company';

/**
 * Hiring signal aggregated across the account's leads. The estimate is a sum of
 * per-lead figures and is labelled as an available-data estimate (§13).
 */
export function HiringIntelligence({ company }: { company: CompanyIntelligence }) {
  const { estimatedHiring, roles } = company.hiring;
  return (
    <DetailCard title="Hiring intelligence">
      <div className="space-y-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">
            Estimated technology hiring
          </p>
          {estimatedHiring > 0 ? (
            <>
              <p className="mt-0.5 text-2xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                {estimatedHiring}
              </p>
              <p className="text-xs text-slate-400 dark:text-slate-500">Estimate based on available lead data.</p>
            </>
          ) : (
            <p className="mt-0.5 text-sm text-slate-400 dark:text-slate-500">Not enough information</p>
          )}
        </div>
        <div>
          <p className="mb-1.5 text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Top roles</p>
          <Chips items={roles} />
        </div>
      </div>
    </DetailCard>
  );
}
