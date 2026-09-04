import { DetailCard, Field } from '@/components/leads/detail/DetailCard';
import type { Lead } from '@/types/lead';

/** Estimated staffing headline (§14) — never an invented estimate. */
function staffingText(estimatedHiring: number | null): string {
  if (estimatedHiring == null || estimatedHiring <= 0) return 'Not enough information';
  return `${estimatedHiring} engineer${estimatedHiring === 1 ? '' : 's'}`;
}

/**
 * Opportunity analysis. The backend persists a summary and an estimated hiring
 * figure; the deeper analysis (staffing band, team size, urgency, confidence)
 * is produced at analysis time and not stored, so it is not shown here.
 */
export function OpportunityPanel({ lead }: { lead: Lead }) {
  return (
    <DetailCard title="Opportunity analysis">
      <dl className="space-y-3">
        <Field label="Summary">{lead.opportunity_summary}</Field>
        <div>
          <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">
            Estimated staffing
          </dt>
          <dd className="mt-0.5 text-lg font-semibold text-slate-900">
            {staffingText(lead.estimated_hiring)}
          </dd>
        </div>
      </dl>
    </DetailCard>
  );
}
