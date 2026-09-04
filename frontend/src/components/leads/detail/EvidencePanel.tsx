import { DetailCard, Field } from '@/components/leads/detail/DetailCard';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import { formatDate, formatDateTime } from '@/utils/format';
import type { Lead } from '@/types/lead';

/**
 * Evidence behind the lead. Presents the single persisted source — it does not
 * claim multi-source validation, which the backend does not provide.
 */
export function EvidencePanel({ lead }: { lead: Lead }) {
  return (
    <DetailCard title="Evidence">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Field label="Source">{lead.source_name}</Field>
        <Field label="Signal date">{formatDate(lead.signal_date)}</Field>
        <Field label="Signal confidence">
          {lead.signal_confidence != null ? `${Math.round(lead.signal_confidence)} / 100` : undefined}
        </Field>
        <div className="col-span-2 sm:col-span-3">
          <Field label="Source URL">
            <ExternalLinkValue href={lead.source_url} stripScheme />
          </Field>
        </div>
        <Field label="Last verified">{formatDateTime(lead.last_verified_at)}</Field>
        <Field label="Created">{formatDateTime(lead.created_at)}</Field>
        <Field label="Updated">{formatDateTime(lead.updated_at)}</Field>
      </dl>
    </DetailCard>
  );
}
