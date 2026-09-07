import type { ReactNode } from 'react';
import { cn } from '@/utils/cn';
import type { DataProvenance, HiringIntensity, LeadPriority } from '@/types/lead';
import { priorityBadgeClass } from '@/utils/format';

export function Badge({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cn('badge bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300', className)}>{children}</span>
  );
}

/** Priority badge — colour + label (never colour alone) for accessibility. */
export function PriorityBadge({ priority }: { priority: LeadPriority }) {
  return <span className={cn('badge', priorityBadgeClass[priority])}>{priority}</span>;
}

const intensityClass: Record<HiringIntensity, string> = {
  LOW: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  MEDIUM: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300',
  HIGH: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300',
  VERY_HIGH: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-300',
};

const intensityLabel: Record<HiringIntensity, string> = {
  LOW: 'Low',
  MEDIUM: 'Medium',
  HIGH: 'High',
  VERY_HIGH: 'Very high',
};

export function HiringIntensityBadge({ intensity }: { intensity: HiringIntensity | null }) {
  if (!intensity) return <span className="text-slate-400 dark:text-slate-500">—</span>;
  return <span className={cn('badge', intensityClass[intensity])}>{intensityLabel[intensity]}</span>;
}

/** Only synthetic/demo data is badged, so real leads carry no extra chrome. */
export function ProvenanceBadge({ provenance }: { provenance: DataProvenance }) {
  if (provenance !== 'SYNTHETIC') return null;
  return (
    <span
      className="badge bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
      title="Demo data — not a real collected signal"
    >
      Demo
    </span>
  );
}
