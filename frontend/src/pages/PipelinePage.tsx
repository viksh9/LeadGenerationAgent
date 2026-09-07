import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Download, RefreshCw } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/Select';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/States';
import { cn } from '@/utils/cn';
import { useCrmAnalytics, usePipelineBoard, useSetOpportunityStage } from '@/hooks/useCrm';
import {
  SALES_STAGES,
  formatPipelineValue,
  formatRate,
  salesStageDisplay,
} from '@/services/crm';
import type { PipelineColumn, SalesOpportunity, SalesStage } from '@/services/crm';
import { rowsToCsv } from '@/services/analytics';

function Kpi({ label, value }: { label: string; value: string | number }) {
  return (
    <Card>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold text-slate-900 dark:text-slate-100">{value}</p>
    </Card>
  );
}

function OpportunityCard({
  opp,
  onRequestStage,
}: {
  opp: SalesOpportunity;
  onRequestStage: (opp: SalesOpportunity, stage: SalesStage) => void;
}) {
  const stage = salesStageDisplay(opp.stage);
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 text-sm font-semibold text-slate-900 dark:text-slate-100">
          {opp.lead_id ? (
            <Link to={`/leads/${opp.lead_id}`} className="hover:underline">
              {opp.title}
            </Link>
          ) : (
            opp.title
          )}
        </p>
        <span className={cn('badge shrink-0', stage.className)}>{stage.label}</span>
      </div>
      {opp.opportunity_type && (
        <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{opp.opportunity_type}</p>
      )}
      <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
        <div>
          <dt className="text-slate-400 dark:text-slate-500">Value</dt>
          <dd className="font-medium text-slate-700 dark:text-slate-300">
            {formatPipelineValue(opp.estimated_value, opp.estimated_value_currency)}
          </dd>
        </div>
        <div>
          <dt className="text-slate-400 dark:text-slate-500">Confidence</dt>
          <dd className="font-medium text-slate-700 dark:text-slate-300">{opp.confidence}</dd>
        </div>
        <div>
          <dt className="text-slate-400 dark:text-slate-500">Probability</dt>
          <dd className="font-medium text-slate-700 dark:text-slate-300">
            {opp.probability === null || opp.probability === undefined
              ? 'Not available'
              : `${opp.probability}%`}
          </dd>
        </div>
      </dl>
      <div className="mt-3">
        <Select
          aria-label={`Change stage for ${opp.title}`}
          className="w-full py-1 text-xs"
          value={opp.stage}
          onChange={(e) => onRequestStage(opp, e.target.value as SalesStage)}
        >
          {SALES_STAGES.map((s) => (
            <option key={s} value={s}>
              {salesStageDisplay(s).label}
            </option>
          ))}
        </Select>
      </div>
    </div>
  );
}

function BoardColumn({
  column,
  onRequestStage,
}: {
  column: PipelineColumn;
  onRequestStage: (opp: SalesOpportunity, stage: SalesStage) => void;
}) {
  const stage = salesStageDisplay(column.stage);
  return (
    <div className="flex w-72 shrink-0 flex-col rounded-xl bg-slate-50 p-3 dark:bg-slate-800/40">
      <div className="mb-3 flex items-center justify-between">
        <span className={cn('badge', stage.className)}>{stage.label}</span>
        <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{column.count}</span>
      </div>
      <div className="space-y-2">
        {column.opportunities.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-200 p-3 text-center text-xs text-slate-400 dark:border-slate-700 dark:text-slate-500">
            No opportunities in this stage.
          </p>
        ) : (
          column.opportunities.map((opp) => (
            <OpportunityCard key={opp.id} opp={opp} onRequestStage={onRequestStage} />
          ))
        )}
      </div>
    </div>
  );
}

export function PipelinePage() {
  const board = usePipelineBoard();
  const analytics = useCrmAnalytics();
  const setStage = useSetOpportunityStage();
  const [pending, setPending] = useState<{ opp: SalesOpportunity; stage: SalesStage } | null>(null);

  const requestStage = (opp: SalesOpportunity, stage: SalesStage) => {
    if (stage === opp.stage) return;
    if (stage === 'WON' || stage === 'LOST') {
      setPending({ opp, stage });
    } else {
      setStage.mutate({ id: opp.id, body: { stage } });
    }
  };

  const confirmStage = () => {
    if (!pending) return;
    setStage.mutate(
      { id: pending.opp.id, body: { stage: pending.stage } },
      { onSuccess: () => setPending(null) },
    );
  };

  const exportCsv = () => {
    const columns = board.data?.columns ?? [];
    const rows = columns.flatMap((col) =>
      col.opportunities.map((o) => [
        o.id,
        o.title,
        salesStageDisplay(o.stage).label,
        o.confidence,
        formatPipelineValue(o.estimated_value, o.estimated_value_currency),
        o.value_source,
        o.probability ?? 'Not available',
        o.lead_id ?? '',
        o.company_id ?? '',
      ]),
    );
    const csv = rowsToCsv(
      ['ID', 'Title', 'Stage', 'Confidence', 'Value', 'Value source', 'Probability', 'Lead ID', 'Company ID'],
      rows,
    );
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'sales-pipeline.csv';
    link.click();
    URL.revokeObjectURL(url);
  };

  const a = analytics.data;
  const hasRows = (board.data?.columns ?? []).some((c) => c.opportunities.length > 0);

  const actions = (
    <div className="flex items-center gap-2">
      <button
        type="button"
        className="btn-secondary text-sm"
        onClick={exportCsv}
        disabled={!hasRows}
        aria-label="Export pipeline CSV"
      >
        <Download className="h-4 w-4" aria-hidden="true" />
        Export CSV
      </button>
      <button
        type="button"
        className="btn-secondary text-sm"
        onClick={() => {
          board.refetch();
          analytics.refetch();
        }}
        disabled={board.isFetching}
        aria-label="Refresh pipeline"
      >
        <RefreshCw className={board.isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
        Refresh
      </button>
    </div>
  );

  return (
    <PageContainer
      title="Sales pipeline"
      subtitle="Real sales opportunities and CRM performance — no figure is shown unless the backend reports it."
      actions={actions}
    >
      <div className="space-y-6">
        {/* CRM analytics KPI strip */}
        {analytics.isLoading ? (
          <Card>
            <p className="text-sm text-slate-500 dark:text-slate-400">Loading CRM analytics…</p>
          </Card>
        ) : analytics.isError ? (
          <ErrorState message="Unable to load CRM analytics." onRetry={() => analytics.refetch()} />
        ) : a ? (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              <Kpi label="Total leads" value={a.total_leads} />
              <Kpi label="Real contacted" value={a.real_contacted} />
              <Kpi label="Real replies" value={a.real_replies} />
              <Kpi label="Real meetings" value={a.real_meetings} />
              <Kpi label="Open opportunities" value={a.open_opportunities} />
              <Kpi label="Won" value={a.won} />
              <Kpi label="Lost" value={a.lost} />
              <Kpi
                label="Pipeline value"
                value={formatPipelineValue(a.pipeline_value, a.pipeline_value_currency)}
              />
            </div>

            {/* Conversion funnel — honest numerator/denominator + rate. */}
            <Card>
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                Conversion funnel
              </h3>
              {a.conversion.length === 0 ? (
                <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                  No sales activity recorded.
                </p>
              ) : (
                <ul className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {a.conversion.map((c) => (
                    <li
                      key={c.label}
                      className="rounded-lg border border-slate-200 p-3 dark:border-slate-800"
                    >
                      <p className="text-sm font-medium text-slate-800 dark:text-slate-200">
                        {c.label}
                      </p>
                      <p className="mt-1 text-lg font-semibold text-slate-900 dark:text-slate-100">
                        {formatRate(c.rate)}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        {c.numerator} / {c.denominator}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </>
        ) : null}

        {/* Kanban board */}
        {board.isLoading ? (
          <LoadingState message="Loading pipeline board…" />
        ) : board.isError ? (
          <ErrorState message="Unable to load the pipeline board." onRetry={() => board.refetch()} />
        ) : !hasRows ? (
          <Card>
            <EmptyState
              title="No real CRM activity available."
              description="Sales opportunities appear here once leads are promoted into the pipeline."
            />
          </Card>
        ) : (
          <div className="flex gap-3 overflow-x-auto pb-2">
            {board.data!.columns.map((col) => (
              <BoardColumn key={col.stage} column={col} onRequestStage={requestStage} />
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        open={pending !== null}
        destructive={pending?.stage === 'LOST'}
        title={
          pending?.stage === 'WON' ? 'Mark opportunity as Won?' : 'Mark opportunity as Lost?'
        }
        description={
          pending
            ? `"${pending.opp.title}" will move to ${salesStageDisplay(pending.stage).label}.`
            : undefined
        }
        confirmLabel={pending ? salesStageDisplay(pending.stage).label : 'Confirm'}
        busy={setStage.isPending}
        onConfirm={confirmStage}
        onCancel={() => setPending(null)}
      />
    </PageContainer>
  );
}
