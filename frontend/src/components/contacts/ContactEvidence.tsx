import { ExternalLink } from 'lucide-react';
import { humanizeSignal } from '@/constants/leads';
import { formatDate } from '@/utils/format';
import type { ContactRecommendation } from '@/types/contact';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-xs uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="text-right text-sm text-slate-700">{children}</dd>
    </div>
  );
}

/** Evidence behind a recommendation — the single persisted source (no multi-source claim). */
export function ContactEvidence({ contact: c }: { contact: ContactRecommendation }) {
  return (
    <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-3">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Evidence</p>
      <dl className="mt-2 space-y-2">
        <Row label="Signal">{c.signalType ? humanizeSignal(c.signalType) : 'Not available'}</Row>
        <Row label="Source">{c.sourceName ?? 'Not available'}</Row>
        <Row label="Date">{formatDate(c.signalDate)}</Row>
        <Row label="Confidence">
          {c.signalConfidence != null ? `${Math.round(c.signalConfidence)}%` : 'Not available'}
        </Row>
      </dl>
      {c.sourceUrl && (
        <a
          href={c.sourceUrl}
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
