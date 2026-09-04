import type { ReactNode } from 'react';
import { cn } from '@/utils/cn';
import type { LeadPriority } from '@/types/lead';
import { priorityBadgeClass } from '@/utils/format';

export function Badge({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cn('badge bg-slate-100 text-slate-700', className)}>{children}</span>
  );
}

/** Priority badge — colour + label (never colour alone) for accessibility. */
export function PriorityBadge({ priority }: { priority: LeadPriority }) {
  return <span className={cn('badge', priorityBadgeClass[priority])}>{priority}</span>;
}
