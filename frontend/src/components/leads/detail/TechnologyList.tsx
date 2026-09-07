import { DetailCard } from '@/components/leads/detail/DetailCard';
import { Chips } from '@/components/leads/detail/primitives';
import type { Lead } from '@/types/lead';

/** Detected technology requirements and likely staffing roles. */
export function TechnologyList({ lead }: { lead: Lead }) {
  return (
    <DetailCard title="Technology & roles">
      <div className="space-y-4">
        <div>
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
            Technology requirements
          </p>
          <Chips items={lead.technologies} />
        </div>
        <div>
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
            Likely roles
          </p>
          <Chips items={lead.hiring_roles} />
        </div>
      </div>
    </DetailCard>
  );
}
