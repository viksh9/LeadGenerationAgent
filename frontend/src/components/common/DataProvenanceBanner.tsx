import { FlaskConical } from 'lucide-react';

/**
 * Shown when the dashboard is displaying synthetic/demo data. Makes it
 * unmistakable that these are NOT real collected Indian IT market signals, so
 * demo data is never mistaken for production intelligence.
 */
export function DataProvenanceBanner() {
  return (
    <div
      role="status"
      className="mb-6 flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800/60 dark:bg-amber-900/20 dark:text-amber-200"
    >
      <FlaskConical className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
      <div>
        <p className="font-semibold">Demo data — no real sources connected yet.</p>
        <p className="mt-0.5 text-amber-800/90 dark:text-amber-200/80">
          These company opportunities are synthetic, generated for development. Connect and verify a
          real Indian IT data source to populate the production dashboard.
        </p>
      </div>
    </div>
  );
}
