import { DetailCard, Field } from '@/components/leads/detail/DetailCard';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import type { Lead } from '@/types/lead';

/**
 * Point-of-contact intelligence. Shows only what is persisted (a recommended
 * name/title and public links). No secondary-role ranking or relevance scores
 * are fabricated — those come from the analysis engine and are not stored.
 */
export function POCPanel({ lead }: { lead: Lead }) {
  const hasContact =
    lead.poc_name || lead.poc_title || lead.poc_linkedin_url || lead.public_contact;

  return (
    <DetailCard title="Point of contact">
      {hasContact ? (
        <dl className="grid grid-cols-2 gap-3">
          <Field label="Name">{lead.poc_name}</Field>
          <Field label="Title">{lead.poc_title}</Field>
          <div className="col-span-2">
            <Field label="LinkedIn">
              <ExternalLinkValue href={lead.poc_linkedin_url} label="View profile" />
            </Field>
          </div>
          <div className="col-span-2">
            <Field label="Public contact">{lead.public_contact}</Field>
          </div>
        </dl>
      ) : (
        <p className="text-sm text-slate-400">No contact identified yet.</p>
      )}
    </DetailCard>
  );
}
