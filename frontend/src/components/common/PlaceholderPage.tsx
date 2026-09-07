import { Construction } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';

/** Reusable "coming next" page for routes not yet implemented. */
export function PlaceholderPage({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <PageContainer title={title} subtitle={subtitle}>
      <Card>
        <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <Construction className="h-8 w-8 text-slate-300 dark:text-slate-600" aria-hidden="true" />
          <p className="text-sm font-medium text-slate-700 dark:text-slate-300">Coming next</p>
          <p className="max-w-sm text-sm text-slate-500 dark:text-slate-400">
            This section is part of the application shell. Its functionality will be implemented in a
            later phase.
          </p>
        </div>
      </Card>
    </PageContainer>
  );
}
