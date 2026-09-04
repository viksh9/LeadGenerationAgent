import { FileText, RefreshCw, Sparkles } from 'lucide-react';
import type { ComponentType } from 'react';
import { Card, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/States';
import { timeAgo } from '@/utils/format';
import type { ActivityItem, ActivityKind } from '@/types/dashboard';

const KIND_META: Record<ActivityKind, { label: string; icon: ComponentType<{ className?: string }> }> = {
  created: { label: 'Lead created', icon: FileText },
  analyzed: { label: 'Lead analyzed', icon: Sparkles },
  updated: { label: 'Lead updated', icon: RefreshCw },
};

export function RecentActivity({ items }: { items: ActivityItem[] }) {
  return (
    <Card padded={false}>
      <div className="px-5 py-4">
        <CardTitle>Recent Activity</CardTitle>
      </div>
      {items.length === 0 ? (
        <EmptyState title="No activity yet" />
      ) : (
        <ul className="divide-y divide-slate-100">
          {items.map((item) => {
            const { label, icon: Icon } = KIND_META[item.kind];
            return (
              <li key={`${item.id}-${item.kind}`} className="flex items-center gap-3 px-5 py-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-500">
                  <Icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-slate-700">
                    <span className="font-medium text-slate-900">{label}</span> — {item.company}
                  </p>
                </div>
                <span className="shrink-0 text-xs text-slate-400">{timeAgo(item.at)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
