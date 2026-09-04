import type { ComponentType } from 'react';
import { Card } from '@/components/ui/Card';

interface DashboardKpiCardProps {
  title: string;
  value: number | string;
  description: string;
  icon: ComponentType<{ className?: string }>;
  accent?: string;
  note?: string;
}

export function DashboardKpiCard({
  title,
  value,
  description,
  icon: Icon,
  accent = 'text-brand-600',
  note,
}: DashboardKpiCardProps) {
  return (
    <Card>
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <p className="text-sm text-slate-500">{title}</p>
          <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">
            {typeof value === 'number' ? value.toLocaleString() : value}
          </p>
          <p className="mt-1 text-xs text-slate-500">{description}</p>
          {note && <p className="mt-1 text-xs text-slate-400">{note}</p>}
        </div>
        <Icon className={`h-8 w-8 shrink-0 ${accent}`} aria-hidden="true" />
      </div>
    </Card>
  );
}
