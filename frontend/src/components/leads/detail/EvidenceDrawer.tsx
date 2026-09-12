import { useEffect, useRef } from 'react';
import { ExternalLink, X } from 'lucide-react';
import { useLeadSources } from '@/hooks/useLeadIntelligence';
import type { SourceRef } from '@/services/intelligence';
import { formatDateTime } from '@/utils/format';

/** Side drawer listing every contributing source for a lead (§35). Read-only,
 *  source-backed; a field with no source URL simply omits the link. Clones the
 *  existing drawer pattern (overlay + Escape + focus) used elsewhere in the app. */
function SourceRow({ s }: { s: SourceRef }) {
  return (
    <div className="rounded-lg border border-slate-100 dark:border-slate-800 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
          {s.field}
        </span>
        <span className="badge bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300">
          {s.source}
        </span>
      </div>
      {s.value && <p className="mt-1 break-words text-sm text-slate-800 dark:text-slate-200">{s.value}</p>}
      <dl className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-500 dark:text-slate-400">
        {s.verification_status && (
          <div>
            <dt className="uppercase tracking-wide text-slate-400 dark:text-slate-500">Status</dt>
            <dd>{s.verification_status}</dd>
          </div>
        )}
        {s.trust_score > 0 && (
          <div>
            <dt className="uppercase tracking-wide text-slate-400 dark:text-slate-500">Trust</dt>
            <dd>{s.trust_score}%</dd>
          </div>
        )}
        {s.last_verified_at && (
          <div>
            <dt className="uppercase tracking-wide text-slate-400 dark:text-slate-500">Last verified</dt>
            <dd>{formatDateTime(s.last_verified_at)}</dd>
          </div>
        )}
        {s.retrieved_at && (
          <div>
            <dt className="uppercase tracking-wide text-slate-400 dark:text-slate-500">Retrieved</dt>
            <dd>{formatDateTime(s.retrieved_at)}</dd>
          </div>
        )}
      </dl>
      {s.evidence && <p className="mt-2 text-xs italic text-slate-500 dark:text-slate-400">{s.evidence}</p>}
      {s.source_url && (
        <a
          href={s.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-sm text-brand-600 hover:underline"
        >
          Open source
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
        </a>
      )}
    </div>
  );
}

export function EvidenceDrawer({ leadId, open, onClose }: { leadId: number; open: boolean; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const sources = useLeadSources(leadId, open);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const rows = sources.data?.sources ?? [];
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Evidence and sources"
        className="h-full w-full max-w-md overflow-y-auto bg-white dark:bg-slate-900 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-slate-100 dark:border-slate-800 p-4">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-slate-900 dark:text-slate-100">Evidence &amp; sources</h2>
            <p className="text-xs text-slate-400 dark:text-slate-500">{sources.data?.company_name ?? '—'}</p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="rounded-md p-1 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-700 dark:hover:text-slate-300"
            onClick={onClose}
            aria-label="Close evidence"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <div className="space-y-3 p-4">
          {sources.isLoading ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">Loading sources…</p>
          ) : sources.isError ? (
            <p className="text-sm text-rose-600 dark:text-rose-400">Unable to load sources.</p>
          ) : rows.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">Source Unavailable.</p>
          ) : (
            rows.map((s, i) => <SourceRow key={`${s.field}-${s.source}-${i}`} s={s} />)
          )}
        </div>
      </div>
    </div>
  );
}
