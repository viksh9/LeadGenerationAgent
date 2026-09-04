import { DetailCard, Field } from '@/components/leads/detail/DetailCard';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import { formatDate } from '@/utils/format';
import type { Lead } from '@/types/lead';

/** Who the company is — persisted profile fields only. */
export function CompanySummaryCard({ lead }: { lead: Lead }) {
  return (
    <DetailCard title="Company summary">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Field label="Industry">{lead.industry}</Field>
        <Field label="Location">{lead.location}</Field>
        <Field label="Company size">{lead.company_size}</Field>
        <Field label="Project">{lead.project_name}</Field>
        <Field label="Estimated hiring">
          {lead.estimated_hiring != null ? `${lead.estimated_hiring}` : undefined}
        </Field>
        <Field label="Signal date">{formatDate(lead.signal_date)}</Field>
        <div className="col-span-2 sm:col-span-1">
          <Field label="Website">
            <ExternalLinkValue href={lead.company_website} stripScheme />
          </Field>
        </div>
        <Field label="Source">{lead.source_name}</Field>
      </dl>
    </DetailCard>
  );
}
