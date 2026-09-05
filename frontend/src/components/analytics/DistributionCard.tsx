import type { ReactNode } from 'react';
import { Card, CardTitle } from '@/components/ui/Card';

/** A titled card wrapping an analytics chart. */
export function DistributionCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardTitle>{title}</CardTitle>
      <div className="mt-3">{children}</div>
    </Card>
  );
}
