import { cn } from '@/utils/cn';
import { OPPORTUNITY_TYPE_LABELS } from '@/services/opportunities';
import type { OpportunityType, StaffingNeed, Urgency } from '@/types/opportunity';

/** Neutral badge naming the (derived) opportunity type. */
export function OpportunityTypeBadge({ type }: { type: OpportunityType }) {
  return <span className="badge bg-slate-100 text-slate-700">{OPPORTUNITY_TYPE_LABELS[type]}</span>;
}

const STAFFING_CLASS: Record<StaffingNeed, string> = {
  HIGH: 'bg-rose-50 text-rose-700 ring-rose-200',
  MEDIUM: 'bg-amber-50 text-amber-700 ring-amber-200',
  LOW: 'bg-blue-50 text-blue-700 ring-blue-200',
  UNKNOWN: 'bg-slate-100 text-slate-600 ring-slate-200',
};

/** Staffing need — label + colour ring (never colour alone). */
export function StaffingNeedBadge({ need }: { need: StaffingNeed }) {
  return <span className={cn('badge ring-1 ring-inset', STAFFING_CLASS[need])}>{need}</span>;
}

const URGENCY_CLASS: Record<Urgency, string> = {
  CRITICAL: 'bg-rose-100 text-rose-800 ring-rose-300',
  HIGH: 'bg-rose-50 text-rose-700 ring-rose-200',
  MEDIUM: 'bg-amber-50 text-amber-700 ring-amber-200',
  LOW: 'bg-slate-100 text-slate-600 ring-slate-200',
  UNKNOWN: 'bg-slate-100 text-slate-500 ring-slate-200',
};

/** Urgency — label + colour ring; optional reason via title tooltip. */
export function UrgencyBadge({ urgency, reason }: { urgency: Urgency; reason?: string | null }) {
  return (
    <span
      className={cn('badge ring-1 ring-inset', URGENCY_CLASS[urgency])}
      title={reason ?? undefined}
    >
      {urgency}
    </span>
  );
}
