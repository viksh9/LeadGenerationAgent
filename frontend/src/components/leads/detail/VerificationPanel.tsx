import { DetailCard, Field } from '@/components/leads/detail/DetailCard';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import { formatDate } from '@/utils/format';
import { useLeadVerification } from '@/hooks/useLeads';
import type { LeadReadiness, VerificationStatus } from '@/types/lead';

// Honest colours — never green just because a record exists.
const STATUS_STYLE: Record<VerificationStatus, string> = {
  VERIFIED: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  PARTIALLY_VERIFIED: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  UNVERIFIED: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200',
  STALE: 'bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200',
  CONTRADICTED: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300',
};
const STATUS_LABEL: Record<VerificationStatus, string> = {
  VERIFIED: 'Verified',
  PARTIALLY_VERIFIED: 'Partially verified',
  UNVERIFIED: 'Unverified',
  STALE: 'Stale',
  CONTRADICTED: 'Contradicted',
};
const READINESS_STYLE: Record<LeadReadiness, string> = {
  READY: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300',
  REVIEW_REQUIRED: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  HOLD: 'bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200',
  DISCARD: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300',
};

function Meter({ label, value }: { label: string; value: number }) {
  const color = value >= 70 ? 'bg-emerald-500' : value >= 45 ? 'bg-amber-500' : 'bg-rose-500';
  return (
    <div>
      <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
        <span>{label}</span>
        <span className="font-medium text-slate-700 dark:text-slate-200">{value}</span>
      </div>
      <div className="mt-1 h-1.5 w-full rounded-full bg-slate-100 dark:bg-slate-800">
        <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${Math.max(2, Math.min(100, value))}%` }} />
      </div>
    </div>
  );
}

export function VerificationPanel({ leadId }: { leadId: number }) {
  const { data: v, isLoading, isError } = useLeadVerification(leadId);

  return (
    <DetailCard title="Evidence Verification">
      {isLoading && <p className="text-sm text-slate-500 dark:text-slate-400">Loading verification…</p>}
      {isError && <p className="text-sm text-rose-600">Unable to load verification.</p>}
      {v && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <span className={`badge ${STATUS_STYLE[v.verification_status]}`}>{STATUS_LABEL[v.verification_status]}</span>
            <span className={`badge ${READINESS_STYLE[v.lead_readiness]}`}>{v.lead_readiness.replace('_', ' ')}</span>
            {v.data_provenance === 'SYNTHETIC' && (
              <span className="badge bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300" title="Demo data">
                Demo
              </span>
            )}
          </div>

          {/* Four DISTINCT scores — deliberately not one number. */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Meter label="Source reliability" value={v.source_reliability} />
            <Meter label="Evidence confidence" value={v.evidence_confidence} />
            <Meter label="Freshness" value={v.freshness_score} />
            <Meter label="Lead score" value={Math.round(v.lead_score)} />
          </div>

          <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Field label="Independent sources">{v.independent_support_count}</Field>
            <Field label="Source references">{v.source_count}</Field>
            <Field label="Verified">{formatDate(v.verified_at)}</Field>
          </dl>
          {v.source_count > v.independent_support_count && (
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {v.source_count - v.independent_support_count} syndicated/duplicate reference(s) not counted as
              independent confirmation.
            </p>
          )}

          {v.verification_reason && (
            <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">{v.verification_reason}</p>
          )}

          {v.conflicts.length > 0 && (
            <div className="mt-4">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-rose-600">Conflicts</p>
              <ul className="space-y-1 text-sm text-rose-700 dark:text-rose-300">
                {v.conflicts.map((c) => (
                  <li key={c.id}>[{c.severity}] {c.conflict_type}: {c.description}</li>
                ))}
              </ul>
            </div>
          )}

          {v.supporting_sources.length > 0 && (
            <div className="mt-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                Supporting sources ({v.supporting_sources.length})
              </p>
              <ul className="divide-y divide-slate-100 dark:divide-slate-800 rounded-md border border-slate-200 dark:border-slate-800">
                {v.supporting_sources.slice(0, 12).map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                    <span className="min-w-0">
                      <span className="block truncate text-slate-800 dark:text-slate-200">
                        {s.evidence_title ?? 'Evidence'}
                      </span>
                      <span className="text-xs text-slate-400 dark:text-slate-500">
                        {s.source_name} · {s.source_tier} · reliability {s.source_reliability_score}
                      </span>
                    </span>
                    <span className="whitespace-nowrap text-xs text-slate-500 dark:text-slate-400">
                      {s.source_url ? <ExternalLinkValue href={s.source_url} stripScheme /> : formatDate(s.published_at)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </DetailCard>
  );
}
