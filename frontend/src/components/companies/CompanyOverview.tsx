import { DetailCard, Field } from '@/components/leads/detail/DetailCard';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import { humanizeSignal } from '@/constants/leads';
import { formatDate, formatScore } from '@/utils/format';
import type { CompanyIntelligence } from '@/types/company';

/** Persisted company facts — "Not available" for anything the leads don't carry. */
export function CompanyOverview({ company }: { company: CompanyIntelligence }) {
  const latest = company.latestSignalType
    ? `${humanizeSignal(company.latestSignalType)} · ${formatDate(company.latestSignal)}`
    : null;
  return (
    <DetailCard title="Company overview">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Field label="Industry">{company.industry}</Field>
        <Field label="Location">{company.location}</Field>
        <Field label="Company size">{company.companySize}</Field>
        <div className="col-span-2 sm:col-span-1">
          <Field label="Website">
            <ExternalLinkValue href={company.website} stripScheme />
          </Field>
        </div>
        <Field label="Leads">{company.leadCount}</Field>
        <Field label="Highest lead score">{`${formatScore(company.bestScore)} / 100`}</Field>
        <div className="col-span-2 sm:col-span-3">
          <Field label="Latest signal">{latest}</Field>
        </div>
      </dl>
    </DetailCard>
  );
}
