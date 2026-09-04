import { Card } from '@/components/ui/Card';

function Shimmer({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-slate-200 ${className}`} />;
}

/** Skeleton mirroring the dashboard layout (cards, table rows, charts). */
export function DashboardSkeleton() {
  return (
    <div aria-hidden="true" data-testid="dashboard-skeleton">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <Shimmer className="h-3 w-24" />
            <Shimmer className="mt-3 h-7 w-16" />
            <Shimmer className="mt-3 h-3 w-32" />
          </Card>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <Shimmer className="h-4 w-40" />
          <Shimmer className="mt-4 h-56 w-full" />
        </Card>
        <Card>
          <Shimmer className="h-4 w-40" />
          <Shimmer className="mt-4 h-56 w-full" />
        </Card>
      </div>

      <div className="mt-6">
        <Card>
          <Shimmer className="h-4 w-40" />
          <div className="mt-4 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Shimmer key={i} className="h-8 w-full" />
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
