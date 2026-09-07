import { DetailCard } from '@/components/leads/detail/DetailCard';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import { formatDate, formatDateTime } from '@/utils/format';
import type { CompanyIntelligence } from '@/types/company';

/**
 * Sources & evidence, one row per lead that carries a source. This does not
 * claim cross-source validation — it simply lists the persisted sources.
 */
export function CompanyEvidence({ company }: { company: CompanyIntelligence }) {
  const evidence = company.evidence;
  return (
    <DetailCard title="Sources & evidence">
      {evidence.length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-slate-500">No sources recorded for this account.</p>
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {evidence.map((item) => (
            <li key={item.leadId} className="py-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-medium text-slate-800 dark:text-slate-200">
                  {item.sourceName ?? 'Source'}
                </span>
                <span className="text-xs text-slate-400 dark:text-slate-500">
                  {item.confidence != null ? `${Math.round(item.confidence)}% confidence` : '—'}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-4 text-xs text-slate-400 dark:text-slate-500">
                <span>Signal: {formatDate(item.signalDate)}</span>
                <span>Verified: {formatDateTime(item.lastVerified)}</span>
                {item.sourceUrl && <ExternalLinkValue href={item.sourceUrl} label="Open source" />}
              </div>
            </li>
          ))}
        </ul>
      )}
    </DetailCard>
  );
}
