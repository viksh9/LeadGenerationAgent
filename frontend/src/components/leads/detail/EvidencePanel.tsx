import { DetailCard, Field } from '@/components/leads/detail/DetailCard';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import { formatDate, formatDateTime } from '@/utils/format';
import { sourceKind, sourceKindDisplay } from '@/services/careerSources';
import type { Lead } from '@/types/lead';

/**
 * Evidence behind a company opportunity: the supporting job postings, how many
 * independent sources confirm them, and provenance. Every lead is explainable —
 * we never show one without its traceable source records.
 */
export function EvidencePanel({ lead }: { lead: Lead }) {
  const evidence = lead.evidence ?? [];
  const shown = evidence.slice(0, 10);
  const extra = evidence.length - shown.length;

  return (
    <DetailCard title="Evidence">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Field label="Data provenance">
          {lead.data_provenance === 'SYNTHETIC' ? 'Synthetic / demo' : 'Real (collected)'}
        </Field>
        <Field label="Independent sources">{lead.source_count}</Field>
        <Field label="IT openings">
          {lead.it_job_count}
          {lead.recent_job_count > 0 ? ` (${lead.recent_job_count} recent)` : ''}
        </Field>
        <Field label="Last signal">{formatDate(lead.last_signal_date ?? lead.signal_date)}</Field>
        <Field label="Sources">{lead.source_name}</Field>
        <Field label="Signal confidence">
          {lead.signal_confidence != null ? `${Math.round(lead.signal_confidence)} / 100` : undefined}
        </Field>
        <div className="col-span-2 sm:col-span-3">
          <Field label="Primary source URL">
            <ExternalLinkValue href={lead.source_url} stripScheme />
          </Field>
        </div>
        <Field label="Last verified">{formatDateTime(lead.last_verified_at)}</Field>
        <Field label="Created">{formatDateTime(lead.created_at)}</Field>
        <Field label="Updated">{formatDateTime(lead.updated_at)}</Field>
      </dl>

      {shown.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Supporting job postings ({evidence.length})
          </p>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800 rounded-md border border-slate-200 dark:border-slate-800">
            {shown.map((ev, i) => {
              const kind = sourceKindDisplay(sourceKind(ev.source));
              return (
                <li key={ev.external_id ?? `${ev.source}-${i}`} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
                  <span className="min-w-0">
                    <span className="block truncate text-slate-800 dark:text-slate-200" title={ev.job_title ?? undefined}>
                      {ev.job_title ?? 'Untitled role'}
                    </span>
                    <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-400 dark:text-slate-500">
                      <span>
                        {ev.source ?? 'source'}
                        {ev.duplicate_of_prior_source ? ' · confirms another source' : ''}
                      </span>
                      {kind && <span className={`badge ${kind.className}`}>{kind.label}</span>}
                    </span>
                  </span>
                  <span className="whitespace-nowrap text-xs text-slate-500 dark:text-slate-400">
                    {formatDate(ev.published_at ?? null)}
                  </span>
                </li>
              );
            })}
          </ul>
          {extra > 0 && (
            <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">+{extra} more posting(s)</p>
          )}
        </div>
      )}
    </DetailCard>
  );
}
