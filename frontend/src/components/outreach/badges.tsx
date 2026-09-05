import { cn } from '@/utils/cn';
import { MESSAGE_STRATEGY_LABELS, OUTREACH_STATUS_LABELS } from '@/services/outreach';
import type { MessageStrategy, OutreachStatus } from '@/types/outreach';

const STATUS_CLASS: Record<OutreachStatus, string> = {
  DRAFT: 'bg-slate-100 text-slate-600 ring-slate-200',
  READY: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  REVIEWED: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
  CONTACTED: 'bg-sky-50 text-sky-700 ring-sky-200',
  RESPONDED: 'bg-violet-50 text-violet-700 ring-violet-200',
  MEETING: 'bg-amber-50 text-amber-700 ring-amber-200',
  FOLLOW_UP: 'bg-amber-50 text-amber-700 ring-amber-200',
  COMPLETED: 'bg-slate-100 text-slate-500 ring-slate-200',
};

/** Preparation status — label + colour ring (never colour alone). */
export function OutreachStatusBadge({ status }: { status: OutreachStatus }) {
  return (
    <span className={cn('badge ring-1 ring-inset', STATUS_CLASS[status])}>
      {OUTREACH_STATUS_LABELS[status]}
    </span>
  );
}

/** Neutral badge naming the (derived) message strategy. */
export function MessageStrategyBadge({ strategy }: { strategy: MessageStrategy }) {
  return <span className="badge bg-slate-100 text-slate-700">{MESSAGE_STRATEGY_LABELS[strategy]}</span>;
}

/** Pitch confidence from the Pitch Generator (not persisted -> "Not available"). */
export function PitchConfidence({ confidence }: { confidence: number | null }) {
  if (confidence == null) return <span className="text-sm text-slate-400">Not available</span>;
  const band = confidence >= 75 ? 'HIGH' : confidence >= 50 ? 'MEDIUM' : 'LOW';
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-sm font-semibold tabular-nums text-slate-700">{Math.round(confidence)}%</span>
      <span className="text-xs font-medium text-slate-500">{band}</span>
    </span>
  );
}
