import { RefreshCw, ShieldCheck } from 'lucide-react';
import { DetailCard, Field } from '@/components/leads/detail/DetailCard';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import { formatDate } from '@/utils/format';
import { useCompanyPublicIntelligence, useDiscoverCompanyIntelligence } from '@/hooks/useOfficialCompany';

const EMERALD = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
const SLATE = 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';

/**
 * Official Company Intelligence — real company profile (website, address, contacts)
 * discovered from the company's own public pages, with a per-field source (clickable
 * source URL) and Data Trust. Only real, source-backed values are shown; missing
 * fields read "Not Publicly Available" — never fabricated.
 */
export function OfficialCompanyPanel({ companyName }: { companyName: string }) {
  const { data, isLoading, isError, refetch } = useCompanyPublicIntelligence(companyName);
  const discover = useDiscoverCompanyIntelligence(companyName);

  const na = 'Not Publicly Available';

  return (
    <DetailCard title="Official Company Intelligence">
      {isLoading && <p className="text-sm text-slate-500 dark:text-slate-400">Loading company profile…</p>}
      {isError && (
        <p className="text-sm text-rose-600 dark:text-rose-400">
          Unable to load company profile.{' '}
          <button type="button" className="btn-ghost text-xs" onClick={() => refetch()}>Try again</button>
        </p>
      )}
      {!isLoading && !isError && !data && (
        <p className="text-sm text-slate-400 dark:text-slate-500">
          No verified company entity yet.
        </p>
      )}
      {!isLoading && !isError && data && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className={`badge ${data.data_trust_score >= 60 ? EMERALD : SLATE}`}
                  title="Company Data Trust">
              <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" /> Data Trust: {data.data_trust_score}%
            </span>
            <button type="button" className="btn-secondary text-xs"
                    onClick={() => discover.mutate(data.company_id)} disabled={discover.isPending}>
              <RefreshCw className={discover.isPending ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} aria-hidden="true" />
              {discover.isPending ? 'Discovering…' : 'Discover'}
            </button>
          </div>

          <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Official Website">
              <ExternalLinkValue href={data.website} stripScheme />
            </Field>
            <Field label="Industry">{data.industry || '—'}</Field>
            <Field label="Address">{data.full_address || na}</Field>
            <Field label="City / State / Country">
              {[data.city, data.state, data.country].filter(Boolean).join(', ') || na}
            </Field>
            <Field label="Business Phone">{data.company_phone || na}</Field>
            <Field label="Business Email">{data.company_email || na}</Field>
            <Field label="LinkedIn">
              <ExternalLinkValue href={data.linkedin_url} stripScheme />
            </Field>
            <Field label="Careers">
              <ExternalLinkValue href={data.careers_url} stripScheme />
            </Field>
            <Field label="GitHub (org)">
              <ExternalLinkValue href={data.github_url} stripScheme />
            </Field>
          </dl>

          {/* Operating vs Registered address kept visibly distinct (§29). */}
          {data.registered_address && (
            <div className="rounded-lg border border-slate-100 dark:border-slate-800 p-3">
              <Field label="Registered Address (OpenCorporates)">{data.registered_address}</Field>
            </div>
          )}

          {/* Legal / company verification (§30) — only fields that exist. */}
          {(data.legal_name || data.company_number || data.company_status || data.india_entity_type) && (
            <div className="rounded-lg border border-slate-100 dark:border-slate-800 p-3">
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
                Legal / Company Verification
              </p>
              <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {data.legal_name && <Field label="Legal Name">{data.legal_name}</Field>}
                {data.company_number && <Field label="Company Number">{data.company_number}</Field>}
                {data.jurisdiction_code && <Field label="Jurisdiction">{data.jurisdiction_code}</Field>}
                {data.company_status && <Field label="Status">{data.company_status}</Field>}
                {data.india_entity_type && <Field label="Entity">{data.india_entity_type.replace(/_/g, ' ')}</Field>}
                {data.registry_url && (
                  <Field label="Registry"><ExternalLinkValue href={data.registry_url} stripScheme /></Field>
                )}
                {data.opencorporates_url && (
                  <Field label="OpenCorporates"><ExternalLinkValue href={data.opencorporates_url} stripScheme /></Field>
                )}
              </dl>
            </div>
          )}

          {data.official_verified_at && (
            <p className="text-xs text-slate-400 dark:text-slate-500">
              Verified: {formatDate(data.official_verified_at)}
            </p>
          )}

          {data.field_sources.length > 0 && (
            <div className="border-t border-slate-100 dark:border-slate-800 pt-3">
              <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
                Sources
              </p>
              <ul className="space-y-1.5">
                {data.field_sources.map((s) => (
                  <li key={`${s.field}-${s.source}`} className="text-xs text-slate-600 dark:text-slate-300">
                    <span className="font-medium">{s.field.replace(/_/g, ' ')}</span> ·{' '}
                    <span className="badge bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                      {s.source}
                    </span>{' '}
                    {s.source_url && (
                      <a href={s.source_url} target="_blank" rel="noreferrer"
                         className="text-blue-600 hover:underline dark:text-blue-400">source</a>
                    )}{' '}
                    · Trust {s.trust_score}%
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </DetailCard>
  );
}
