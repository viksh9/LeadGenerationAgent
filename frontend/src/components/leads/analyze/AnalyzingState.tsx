import { Loader2 } from 'lucide-react';

const STAGES = [
  'Reading business signal',
  'Detecting opportunity',
  'Calculating lead score',
  'Identifying target role',
  'Generating outreach pitch',
];

/**
 * Shown while the analysis pipeline runs. Stages reflect the backend pipeline
 * order; there are no fake per-step completions or progress percentages — the
 * whole run is indeterminate.
 */
export function AnalyzingState() {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
      role="status"
      aria-live="polite"
    >
      <div className="w-full max-w-sm rounded-lg bg-white p-6 text-center shadow-xl dark:bg-slate-900">
        <Loader2 className="mx-auto h-6 w-6 animate-spin text-brand-600" aria-hidden="true" />
        <h2 className="mt-3 text-base font-semibold text-slate-900 dark:text-slate-100">Analyzing lead</h2>
        <ul className="mt-4 space-y-2 text-left">
          {STAGES.map((stage) => (
            <li key={stage} className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" aria-hidden="true" />
              {stage}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
