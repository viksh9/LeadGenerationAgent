import { Card, CardTitle } from '@/components/ui/Card';
import { ErrorState, LoadingState } from '@/components/ui/States';
import { useSources } from '@/hooks/useSources';
import {
  connectionStatusDisplay,
  sourceStatusDisplay,
} from '@/services/sources';

/**
 * Compact "Real Data Sources" coverage panel for the Dashboard (§37). Shows the
 * actual per-source configuration + live connection status and last successful
 * collection — all real operational values from GET /sources. No fake metrics.
 */
export function SourceCoverage() {
  const { data, isLoading, isError, refetch } = useSources();

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <CardTitle>Real Data Sources</CardTitle>
        {data ? (
          <span className="text-xs text-slate-500 dark:text-slate-400">
            {data.connected_count} connected · {data.configured_count} configured · {data.total} total
          </span>
        ) : null}
      </div>

      {isLoading ? (
        <LoadingState message="Loading source status…" />
      ) : isError ? (
        <ErrorState message="Unable to load source status." onRetry={refetch} />
      ) : !data || data.items.length === 0 ? (
        <p className="text-sm text-slate-500 dark:text-slate-400">No data sources registered.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wide text-slate-400">
                <th className="py-1 pr-3">Source</th>
                <th className="py-1 pr-3">Category</th>
                <th className="py-1 pr-3">Configuration</th>
                <th className="py-1 pr-3">Connection</th>
                <th className="py-1 pr-3">Last success</th>
                <th className="py-1 pr-3 text-right">Records</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((s) => {
                const cfg = sourceStatusDisplay(s.status);
                const conn = s.connection_status ? connectionStatusDisplay(s.connection_status) : null;
                return (
                  <tr key={s.source_id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1.5 pr-3 font-medium text-slate-700 dark:text-slate-200">
                      {s.name}
                    </td>
                    <td className="py-1.5 pr-3 text-slate-500 dark:text-slate-400">{s.category}</td>
                    <td className="py-1.5 pr-3">
                      <span className={`badge ${cfg.className}`}>{cfg.label}</span>
                    </td>
                    <td className="py-1.5 pr-3">
                      {conn ? (
                        <span className={`badge ${conn.className}`}>{conn.label}</span>
                      ) : (
                        <span className="text-xs text-slate-400">Not checked</span>
                      )}
                    </td>
                    <td className="py-1.5 pr-3 text-slate-500 dark:text-slate-400">
                      {s.last_success_at ? new Date(s.last_success_at).toLocaleString() : '—'}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular-nums text-slate-600 dark:text-slate-300">
                      {s.last_ingestion_records_persisted ?? '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
