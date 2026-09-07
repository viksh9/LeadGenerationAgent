import { Clock } from 'lucide-react';
import { Card, CardTitle } from '@/components/ui/Card';

/**
 * Follow-up queue. No outreach activity dates are persisted yet, so this shows a
 * clear placeholder rather than inventing "contacted N days ago" data (§24).
 */
export function FollowUpQueue() {
  return (
    <Card>
      <CardTitle>Follow-up queue</CardTitle>
      <div className="mt-3 flex items-start gap-2 text-sm text-slate-500 dark:text-slate-400">
        <Clock className="mt-0.5 h-4 w-4 shrink-0 text-slate-400 dark:text-slate-500" aria-hidden="true" />
        <p>Follow-up tracking will be available after outreach activity tracking is implemented.</p>
      </div>
    </Card>
  );
}
