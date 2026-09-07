import { Card, CardTitle } from '@/components/ui/Card';
import type { TopTargetRole } from '@/types/contact';

/** Most-frequently recommended roles with average relevance (§23). */
export function TopTargetRoles({ roles }: { roles: TopTargetRole[] }) {
  if (roles.length === 0) return null;
  return (
    <Card>
      <CardTitle>Top target roles</CardTitle>
      <ul className="mt-3 space-y-2">
        {roles.map((r) => (
          <li key={r.role} className="flex items-center justify-between gap-3">
            <span className="min-w-0 truncate text-sm font-medium text-slate-800 dark:text-slate-200">{r.role}</span>
            <span className="flex shrink-0 items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
              <span className="tabular-nums">{r.avgRelevance} avg</span>
              <span className="tabular-nums">
                {r.count} rec{r.count === 1 ? '' : 's'}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
