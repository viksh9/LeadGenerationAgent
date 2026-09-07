import { cn } from '@/utils/cn';
import { DECISION_MAKER_TYPE_LABELS } from '@/services/contacts';
import type { DecisionMakerType } from '@/types/contact';

/** Neutral badge naming a recommended role. */
export function RoleBadge({ role }: { role: string }) {
  return <span className="badge bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">{role}</span>;
}

const TYPE_CLASS: Record<DecisionMakerType, string> = {
  TECHNICAL: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
  BUSINESS: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  DELIVERY: 'bg-sky-50 text-sky-700 ring-sky-200',
  PROCUREMENT: 'bg-amber-50 text-amber-700 ring-amber-200',
  VENDOR: 'bg-purple-50 text-purple-700 ring-purple-200',
  HR: 'bg-rose-50 text-rose-700 ring-rose-200',
};

/** Decision-maker category — readable label + colour ring (never colour alone). */
export function DecisionMakerTypeBadge({ type }: { type: DecisionMakerType }) {
  return (
    <span className={cn('badge ring-1 ring-inset', TYPE_CLASS[type])}>
      {DECISION_MAKER_TYPE_LABELS[type]}
    </span>
  );
}
