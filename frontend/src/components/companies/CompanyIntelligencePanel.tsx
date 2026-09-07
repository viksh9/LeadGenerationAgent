import { Card } from '@/components/ui/Card';
import { useCompanyIntelligence } from '@/hooks/useCompanyIntelligence';

const VERIF_STYLE: Record<string, string> = {
  VERIFIED: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  PARTIALLY_VERIFIED: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  UNVERIFIED: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200',
  STALE: 'bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200',
  CONTRADICTED: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300',
};
const STRENGTH_STYLE: Record<string, string> = {
  HIGH: 'text-emerald-600',
  MEDIUM: 'text-amber-600',
  LOW: 'text-slate-500',
};

export function CompanyIntelligencePanel({ name }: { name: string }) {
  const { data, isLoading, isError } = useCompanyIntelligence(name);

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
          Company Intelligence (verified backend)
        </h3>
        {data?.company?.data_provenance === 'SYNTHETIC' && (
          <span className="badge bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">Demo</span>
        )}
      </div>

      {isLoading && <p className="text-sm text-slate-500 dark:text-slate-400">Loading…</p>}
      {(isError || (!isLoading && !data)) && (
        <p className="text-sm text-slate-500 dark:text-slate-400">No verified backend company data available yet.</p>
      )}

      {data && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className={`badge ${VERIF_STYLE[data.company.verification_status] ?? ''}`}>
              {data.company.verification_status.replace('_', ' ')}
            </span>
            {data.company.company_type && <span className="badge">{data.company.company_type}</span>}
            {data.company.india_presence && (
              <span className="badge bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
                India: {data.company.india_locations.join(', ') || 'yes'}
              </span>
            )}
          </div>

          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-sm">
            <div><dt className="text-xs text-slate-400">Active openings</dt><dd className="font-medium">{data.profile.hiring.canonical_active_openings}</dd></div>
            <div><dt className="text-xs text-slate-400">Recent</dt><dd className="font-medium">{data.profile.hiring.recent_openings}</dd></div>
            <div><dt className="text-xs text-slate-400">Hiring trend</dt><dd className="font-medium">{data.profile.hiring.hiring_trend.replace('_', ' ')}</dd></div>
            <div><dt className="text-xs text-slate-400">Identity conf.</dt><dd className="font-medium">{data.company.identity_confidence}</dd></div>
          </dl>

          {data.profile.technology_demand.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Technology demand</p>
              <div className="flex flex-wrap gap-2">
                {data.profile.technology_demand.slice(0, 10).map((t) => (
                  <span key={t.technology} className="badge">
                    {t.technology} <span className={STRENGTH_STYLE[t.demand_strength]}>·{t.active_jobs}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 text-sm">
            <div><dt className="text-xs text-slate-400">Verification</dt><dd className="font-medium">{data.profile.evidence.verification_status.replace('_', ' ')}</dd></div>
            <div><dt className="text-xs text-slate-400">Evidence conf.</dt><dd className="font-medium">{data.profile.evidence.evidence_confidence}</dd></div>
            <div><dt className="text-xs text-slate-400">Source reliability</dt><dd className="font-medium">{data.profile.evidence.source_reliability}</dd></div>
            <div><dt className="text-xs text-slate-400">Independent sources</dt><dd className="font-medium">{data.profile.evidence.independent_support_count}</dd></div>
          </div>

          <p className="text-xs text-slate-400 dark:text-slate-500">{data.profile.location_intelligence.note}</p>

          {data.history.length > 0 && (
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">History</p>
              <ul className="space-y-1 text-xs text-slate-500 dark:text-slate-400">
                {data.history.slice(0, 5).map((e, i) => (
                  <li key={i}>· {e.description}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
