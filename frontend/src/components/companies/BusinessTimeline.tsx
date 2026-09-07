import { DetailCard } from '@/components/leads/detail/DetailCard';
import { Badge } from '@/components/ui/Badge';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import { formatDate } from '@/utils/format';
import { useSignals } from '@/hooks/useSignals';
import { useTenders } from '@/hooks/useTenders';
import { signalStrengthDisplay } from '@/services/signals';
import { tenderStatusDisplay } from '@/services/tenders';
import type { CompanyIntelligence } from '@/types/company';

type TimelineEntry = {
  key: string;
  kind: 'SIGNAL' | 'TENDER';
  date: string | null;
  type: string;
  title: string;
  sourceUrl: string | null;
  badge: { label: string; className: string };
};

/**
 * A merged, chronological view of the account's real business events, built
 * client-side from GET /signals?company=<name> and GET /tenders?organization=<name>.
 * Companies are keyed by name here (derived from /leads), so there is no numeric
 * company_id to call /companies/{id}/timeline with — we merge the name-filtered
 * feeds and sort newest first. Nothing is fabricated.
 */
export function BusinessTimeline({ company }: { company: CompanyIntelligence }) {
  const name = company.name;
  const signalsQuery = useSignals({ company: name, page_size: 50 });
  const tendersQuery = useTenders({ organization: name, page_size: 50 });

  const isLoading = signalsQuery.isLoading || tendersQuery.isLoading;
  const isError = signalsQuery.isError || tendersQuery.isError;

  const entries: TimelineEntry[] = [];

  for (const s of signalsQuery.data?.items ?? []) {
    entries.push({
      key: `signal-${s.id}`,
      kind: 'SIGNAL',
      date: s.published_at,
      type: s.signal_type,
      title: s.signal_title ?? s.signal_description ?? s.signal_type,
      sourceUrl: s.signal_url,
      badge: signalStrengthDisplay(s.signal_strength),
    });
  }

  for (const t of tendersQuery.data?.items ?? []) {
    entries.push({
      key: `tender-${t.id}`,
      kind: 'TENDER',
      date: t.publication_date ?? t.issue_date ?? t.closing_date,
      type: t.category ?? 'Tender',
      title: t.title,
      sourceUrl: t.source_url,
      badge: tenderStatusDisplay(t.tender_status),
    });
  }

  // Newest first; undated events sink to the bottom.
  entries.sort((a, b) => {
    const at = a.date ? new Date(a.date).getTime() : -Infinity;
    const bt = b.date ? new Date(b.date).getTime() : -Infinity;
    return bt - at;
  });

  return (
    <DetailCard title="Business timeline">
      {isLoading && (
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading business events…</p>
      )}
      {!isLoading && isError && (
        <p className="text-sm text-rose-600">Unable to load business events.</p>
      )}
      {!isLoading && !isError && entries.length === 0 && (
        <p className="text-sm text-slate-400 dark:text-slate-500">No business events recorded yet.</p>
      )}
      {!isLoading && !isError && entries.length > 0 && (
        <ol className="relative space-y-4 border-l border-slate-200 dark:border-slate-800 pl-5">
          {entries.map((e) => (
            <li key={e.key} className="relative">
              <span
                className="absolute -left-[1.42rem] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-brand-500"
                aria-hidden="true"
              />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge>{e.kind === 'SIGNAL' ? 'Signal' : 'Tender'}</Badge>
                  <span className="text-xs text-slate-500 dark:text-slate-400">{e.type}</span>
                  <span className={`badge ${e.badge.className}`}>{e.badge.label}</span>
                </div>
                <span className="text-xs text-slate-400 dark:text-slate-500">{formatDate(e.date)}</span>
              </div>
              <p className="mt-1 text-sm font-medium text-slate-800 dark:text-slate-200">{e.title}</p>
              {e.sourceUrl && (
                <div className="mt-1 text-xs">
                  <ExternalLinkValue href={e.sourceUrl} label="View source" />
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
    </DetailCard>
  );
}
