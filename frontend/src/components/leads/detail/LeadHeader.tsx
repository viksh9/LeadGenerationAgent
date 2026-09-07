import { RefreshCw, Trash2 } from 'lucide-react';
import { PriorityBadge } from '@/components/ui/Badge';
import { ScoreIndicator } from '@/components/common/ScoreIndicator';
import { StatusControl } from '@/components/leads/detail/StatusControl';
import { formatScore } from '@/utils/format';
import type { Lead } from '@/types/lead';

/**
 * The lead's identity + score + priority + lifecycle controls. Actions are
 * limited to what the backend supports: status change (PUT), a data refresh
 * (re-fetch of GET /leads/{id}), and delete (DELETE).
 */
export function LeadHeader({
  lead,
  onRefresh,
  refreshing,
  onDelete,
  deleting,
}: {
  lead: Lead;
  onRefresh: () => void;
  refreshing: boolean;
  onDelete: () => void;
  deleting: boolean;
}) {
  const subtitle = [lead.industry, lead.location].filter(Boolean).join(' • ') || 'No company details';

  return (
    <section className="card card-pad" aria-label="Lead summary">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <PriorityBadge priority={lead.lead_priority} />
            <span className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
              {lead.status}
            </span>
          </div>
          <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>
        </div>

        <div className="flex flex-wrap items-center gap-4">
          <div className="text-right">
            <p className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Lead score</p>
            <p className="text-2xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">
              {formatScore(lead.lead_score)}
              <span className="text-sm font-normal text-slate-400 dark:text-slate-500"> / 100</span>
            </p>
          </div>
          <ScoreIndicator score={lead.lead_score} />
          <StatusControl leadId={lead.id} status={lead.status} />
          <button
            type="button"
            className="btn-secondary text-sm"
            onClick={onRefresh}
            disabled={refreshing}
            aria-label="Refresh lead"
          >
            <RefreshCw className={refreshing ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
            Refresh
          </button>
          <button
            type="button"
            className="btn-secondary text-sm text-rose-600"
            onClick={onDelete}
            disabled={deleting}
            aria-label="Delete lead"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
            Delete
          </button>
        </div>
      </div>
    </section>
  );
}
