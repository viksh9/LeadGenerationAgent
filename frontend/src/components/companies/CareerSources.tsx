import { DetailCard, Field } from '@/components/leads/detail/DetailCard';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import { formatDateTime } from '@/utils/format';
import { useCareerSources } from '@/hooks/useCareerSources';
import { careerStatusDisplay, providerLabel } from '@/services/careerSources';
import type { CompanyIntelligence } from '@/types/company';

/**
 * Official career sources (ATS boards / company career pages) discovered for an
 * account. Companies here are keyed by name (derived from /leads), so matching
 * is by company_name, case-insensitive. Every source shown is a direct
 * first-party source (TIER_1) — never an aggregator.
 */
export function CareerSources({ company }: { company: CompanyIntelligence }) {
  const { data, isLoading, isError } = useCareerSources();

  const target = company.name.trim().toLowerCase();
  const sources = (data?.items ?? []).filter(
    (s) => (s.company_name ?? '').trim().toLowerCase() === target,
  );

  return (
    <DetailCard title="Official career sources">
      {isLoading && (
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading career sources…</p>
      )}
      {isError && (
        <p className="text-sm text-rose-600">Unable to load career sources.</p>
      )}
      {!isLoading && !isError && sources.length === 0 && (
        <p className="text-sm text-slate-400 dark:text-slate-500">
          No official career source discovered yet.
        </p>
      )}
      {!isLoading && !isError && sources.length > 0 && (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {sources.map((s) => {
            const status = careerStatusDisplay(s.status);
            return (
              <li key={s.id} className="py-3 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium text-slate-800 dark:text-slate-200">
                    {providerLabel(s.ats_provider)}
                  </span>
                  <span className={`badge ${status.className}`}>{status.label}</span>
                </div>
                <div className="mt-1">
                  <span className="badge bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300">
                    Direct official source · TIER_1
                  </span>
                </div>
                <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <Field label="Board identifier">{s.board_identifier}</Field>
                  <Field label="Careers URL">
                    <ExternalLinkValue href={s.careers_url} stripScheme />
                  </Field>
                  <Field label="Last checked">{formatDateTime(s.last_checked_at)}</Field>
                  <Field label="Last successful">{formatDateTime(s.last_success_at)}</Field>
                </dl>
                {s.last_error && (
                  <p className="mt-2 text-xs text-rose-600 dark:text-rose-400">{s.last_error}</p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </DetailCard>
  );
}
