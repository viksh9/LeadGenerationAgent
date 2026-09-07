import { ExternalLink } from 'lucide-react';
import { humanizeSignal } from '@/constants/leads';
import { formatDate } from '@/utils/format';
import type { OutreachItem } from '@/types/outreach';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</dt>
      <dd className="text-right text-sm text-slate-700 dark:text-slate-300">{children}</dd>
    </div>
  );
}

/** Evidence behind the outreach — the single persisted source (no multi-source claim). */
export function EvidenceSummary({ item }: { item: OutreachItem }) {
  return (
    <div className="rounded-lg border border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40 p-3">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">Evidence</p>
      <dl className="mt-2 space-y-2">
        <Row label="Signal">{item.signalType ? humanizeSignal(item.signalType) : 'Not available'}</Row>
        <Row label="Source">{item.sourceName ?? 'Not available'}</Row>
        <Row label="Signal date">{formatDate(item.signalDate)}</Row>
        <Row label="Confidence">
          {item.signalConfidence != null ? `${Math.round(item.signalConfidence)}%` : 'Not available'}
        </Row>
      </dl>
      {item.sourceUrl && (
        <a
          href={item.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-sm text-brand-600 hover:underline"
        >
          View source
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
        </a>
      )}
    </div>
  );
}
