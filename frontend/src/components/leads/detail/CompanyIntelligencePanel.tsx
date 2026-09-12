import { DetailCard } from '@/components/leads/detail/DetailCard';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import { useLeadIntelligence } from '@/hooks/useLeadIntelligence';
import type { LeadIntelligence, SourceRef } from '@/services/intelligence';

/**
 * Company intelligence (§9-§10): identity + location & website, sourced only from the
 * aggregated real intelligence endpoint. Registered vs Operating address are kept
 * distinct. A source badge appears beside a value ONLY when provenance exists for it;
 * missing values show honest empty states (never fabricated).
 */
function SourceBadge({ src }: { src: SourceRef | undefined }) {
  if (!src) return null;
  const inner = (
    <span className="badge bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300">{src.source}</span>
  );
  return src.source_url ? (
    <a href={src.source_url} target="_blank" rel="noopener noreferrer" title={`Source: ${src.source}`}>
      {inner}
    </a>
  ) : (
    inner
  );
}

/** A label / value / source-badge row. Shows `empty` text when there is no value. */
function ProvField({ label, value, src, empty, link }: {
  label: string; value: string | null | undefined; src?: SourceRef; empty: string; link?: boolean;
}) {
  const has = value != null && String(value).trim() !== '';
  return (
    <div>
      <dt className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
        {label}
        {has && <SourceBadge src={src} />}
      </dt>
      <dd className="mt-0.5 break-words text-sm text-slate-800 dark:text-slate-200">
        {has ? (link ? <ExternalLinkValue href={value} stripScheme /> : value)
             : <span className="text-slate-400 dark:text-slate-500">{empty}</span>}
      </dd>
    </div>
  );
}

function sourceFor(intel: LeadIntelligence, field: string): SourceRef | undefined {
  return intel.sources.find((s) => s.field === field);
}

function valueFor(intel: LeadIntelligence, field: string): string | null {
  return sourceFor(intel, field)?.value ?? null;
}

export function CompanyIntelligencePanel({ leadId }: { leadId: number }) {
  const intel = useLeadIntelligence(leadId);

  if (intel.isLoading) {
    return <DetailCard title="Company intelligence"><p className="text-sm text-slate-500 dark:text-slate-400">Loading company intelligence…</p></DetailCard>;
  }
  if (intel.isError || !intel.data) {
    return <DetailCard title="Company intelligence"><p className="text-sm text-rose-600 dark:text-rose-400">Company intelligence unavailable.</p></DetailCard>;
  }

  const d = intel.data;
  const p = d.company_profile;
  const src = (f: string) => sourceFor(d, f);

  return (
    <DetailCard title="Company intelligence">
      {/* Identity */}
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">Identity</p>
      <dl className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <ProvField label="Company" value={p.company_name} empty="No verified company." />
        <ProvField label="Legal name" value={valueFor(d, 'legal_name')} src={src('legal_name')} empty="Not verified" />
        <ProvField label="Registration ID" value={valueFor(d, 'company_number')} src={src('company_number')} empty="Not verified" />
        <ProvField label="Industry" value={p.industry} empty="Not verified" />
        <ProvField label="Company status" value={valueFor(d, 'company_status')} src={src('company_status')} empty="Unknown" />
        <ProvField label="India presence" value={p.india_presence === 'UNKNOWN' ? null : p.india_presence} empty="Unknown" />
      </dl>

      {/* Location & website */}
      <p className="mt-5 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">Location &amp; website</p>
      <dl className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
        <ProvField label="Website" value={p.website} src={src('website_url')} empty="No verified website available." link />
        <ProvField label="Careers" value={p.career_site} src={src('careers_url')} empty="No verified careers URL." link />
        <ProvField label="Leadership / contact" value={valueFor(d, 'leadership_url') ?? valueFor(d, 'contact_url')}
          src={src('leadership_url') ?? src('contact_url')} empty="Not verified" link />
        <ProvField label="LinkedIn" value={valueFor(d, 'linkedin_url')} src={src('linkedin_url')} empty="Not verified" link />
        <ProvField label="GitHub" value={valueFor(d, 'github_url')} src={src('github_url')} empty="Not verified" link />
        <ProvField label="Operating address" value={p.primary_location} src={src('address')} empty="No verified company address available." />
        <ProvField label="Registered address" value={p.registered_location} src={src('registered_address')} empty="No verified registered address." />
      </dl>
    </DetailCard>
  );
}
