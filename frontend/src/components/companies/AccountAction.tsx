import { Target } from 'lucide-react';
import { PriorityBadge } from '@/components/ui/Badge';
import { CopyButton } from '@/components/leads/detail/primitives';
import type { CompanyIntelligence } from '@/types/company';

/**
 * Recommended account action, taken from the strongest related lead's
 * recommendation (or a monitoring hint when evidence is thin). No invented
 * deadlines or claims.
 */
export function AccountAction({ company }: { company: CompanyIntelligence }) {
  const topRole = company.decisionMakers[0]?.role ?? null;
  return (
    <section className="card card-pad" aria-label="Recommended account action">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-slate-100">
        <Target className="h-4 w-4 text-brand-600" aria-hidden="true" />
        Recommended action
      </h3>
      <p className="mt-2 text-sm leading-relaxed text-slate-700 dark:text-slate-300">{company.recommendedAction}</p>
      <div className="mt-2 flex justify-end">
        <CopyButton text={company.recommendedAction} label="Copy recommended action" />
      </div>
      <dl className="mt-3 space-y-2 border-t border-slate-100 dark:border-slate-800 pt-3">
        <div className="flex items-center justify-between">
          <dt className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Account priority</dt>
          <dd>
            <PriorityBadge priority={company.topPriority} />
          </dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Suggested POC</dt>
          <dd className="truncate text-right text-sm text-slate-700 dark:text-slate-300">{topRole ?? 'Not available'}</dd>
        </div>
      </dl>
    </section>
  );
}
