import { Badge } from '@/components/ui/Badge';
import { DetailCard, Field } from '@/components/leads/detail/DetailCard';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import { SignalStrength } from '@/components/leads/detail/SignalStrength';
import { humanizeSignal } from '@/constants/leads';
import { formatDate } from '@/utils/format';
import type { Lead } from '@/types/lead';

/**
 * The business signal that surfaced this lead. The stored lead carries a single
 * signal (type/title/description) — richer multi-signal analysis is produced at
 * analysis time and not persisted, so it is not shown here.
 */
export function SignalPanel({ lead }: { lead: Lead }) {
  return (
    <DetailCard title="Business signal">
      <dl className="grid grid-cols-2 gap-3">
        <Field label="Type">
          {lead.signal_type ? <Badge>{humanizeSignal(lead.signal_type)}</Badge> : undefined}
        </Field>
        <Field label="Strength">
          <SignalStrength confidence={lead.signal_confidence} />
        </Field>
        <div className="col-span-2">
          <Field label="Title">{lead.signal_title}</Field>
        </div>
        <div className="col-span-2">
          <Field label="Reason">{lead.signal_description}</Field>
        </div>
        <Field label="Detected">{formatDate(lead.signal_date)}</Field>
        <Field label="Source">{lead.source_name}</Field>
        <div className="col-span-2">
          <Field label="Source URL">
            <ExternalLinkValue href={lead.source_url} stripScheme />
          </Field>
        </div>
      </dl>
    </DetailCard>
  );
}
