import type { ReactNode } from 'react';
import { Card } from '@/components/ui/Card';

/** A titled section card used across the lead detail view. */
export function DetailCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card padded={false}>
      <h3 className="border-b border-slate-100 dark:border-slate-800 px-5 py-3 text-sm font-semibold text-slate-900 dark:text-slate-100">
        {title}
      </h3>
      <div className="px-5 py-4">{children}</div>
    </Card>
  );
}

/** A label/value pair (renders "—" when empty). */
export function Field({ label, children }: { label: string; children?: ReactNode }) {
  const isEmpty = children === null || children === undefined || children === '';
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</dt>
      <dd className="mt-0.5 break-words text-sm text-slate-800 dark:text-slate-200">{isEmpty ? '—' : children}</dd>
    </div>
  );
}
