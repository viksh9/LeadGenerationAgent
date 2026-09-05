import { relevanceBand } from '@/services/contacts';

const BAND_COLOR = { HIGH: '#059669', MEDIUM: '#d97706', LOW: '#64748b' } as const;

/**
 * Role relevance: number + band label (HIGH/MEDIUM/LOW) + bar. Meaning never
 * depends on colour alone. Relevance is the related lead's score (Phase-1 proxy).
 */
export function RelevanceScore({ relevance }: { relevance: number }) {
  const value = Math.max(0, Math.min(100, Math.round(relevance)));
  const band = relevanceBand(value);
  return (
    <div className="flex items-center gap-2" aria-label={`Relevance ${value} of 100, ${band}`}>
      <div className="flex flex-col">
        <span className="text-sm font-semibold tabular-nums text-slate-900">
          {value}
          <span className="text-xs font-normal text-slate-400"> / 100</span>
        </span>
        <span className="mt-1 h-1.5 w-16 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
          <span
            className="block h-full rounded-full"
            style={{ width: `${value}%`, backgroundColor: BAND_COLOR[band] }}
          />
        </span>
      </div>
      <span className="text-xs font-medium text-slate-500">{band}</span>
    </div>
  );
}
