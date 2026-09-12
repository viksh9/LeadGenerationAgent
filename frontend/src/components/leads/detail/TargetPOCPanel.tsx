import { RefreshCw, Search } from 'lucide-react';
import { DetailCard, Field } from '@/components/leads/detail/DetailCard';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import { formatDateTime } from '@/utils/format';
import { useDiscoverPocs, useDiscoverPublicIntelligence, useLeadPocs } from '@/hooks/useContactOut';
import { contactTrustDisplay, type POC, type RecommendedRole } from '@/services/contactOut';

/**
 * Target POC — real people from ContactOut when discovered/verified, otherwise
 * clearly-labelled role recommendations (never a fabricated name). Work email /
 * business phone are shown only when ContactOut actually returned them.
 */
export function TargetPOCPanel({ leadId }: { leadId: number }) {
  const { data, isLoading, isError, refetch } = useLeadPocs(leadId);
  const discover = useDiscoverPocs(leadId);
  const discoverPublic = useDiscoverPublicIntelligence(leadId);

  const configured = data?.contactout_status === 'CONFIGURED';
  const pocs = data?.pocs ?? [];
  const roles = data?.recommended_roles ?? [];

  const discoverButton = configured ? (
    <button
      type="button"
      className="btn-secondary text-xs"
      onClick={() => discover.mutate({ force: pocs.length > 0 })}
      disabled={discover.isPending}
    >
      {pocs.length > 0 ? (
        <RefreshCw className={discover.isPending ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} aria-hidden="true" />
      ) : (
        <Search className={discover.isPending ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} aria-hidden="true" />
      )}
      {discover.isPending ? 'Searching…' : pocs.length > 0 ? 'Refresh' : 'Discover POCs'}
    </button>
  ) : null;

  return (
    <DetailCard title="Target POC">
      {isLoading && <p className="text-sm text-slate-500 dark:text-slate-400">Loading POCs…</p>}
      {isError && (
        <p className="text-sm text-rose-600 dark:text-rose-400">
          Unable to load POCs.{' '}
          <button type="button" className="btn-ghost text-xs" onClick={() => refetch()}>Try again</button>
        </p>
      )}

      {!isLoading && !isError && data && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-slate-400 dark:text-slate-500">
              {configured ? 'ContactOut + public sources' : 'Free public sources'}
            </p>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="btn-secondary text-xs"
                onClick={() => discoverPublic.mutate({ force: pocs.length > 0 })}
                disabled={discoverPublic.isPending}
                title="Official website, GitHub, Wikidata"
              >
                <Search className={discoverPublic.isPending ? 'h-3.5 w-3.5 animate-spin' : 'h-3.5 w-3.5'} aria-hidden="true" />
                {discoverPublic.isPending ? 'Searching…' : 'Public sources'}
              </button>
              {discoverButton}
            </div>
          </div>

          {/* Real people (Primary / Secondary). */}
          {pocs.length > 0 ? (
            <ul className="space-y-4">
              {pocs.slice(0, 5).map((poc, i) => (
                <li key={poc.id}>
                  <PocRow poc={poc} rank={i === 0 ? 'Primary POC' : 'Secondary POC'} />
                </li>
              ))}
            </ul>
          ) : (
            <>
              {!configured ? (
                <p className="text-sm text-slate-400 dark:text-slate-500">
                  POC enrichment is not configured.
                </p>
              ) : (
                <p className="text-sm text-slate-400 dark:text-slate-500">
                  No verified POC found for this opportunity yet.
                </p>
              )}
              {roles.length > 0 && <RoleRecommendations roles={roles} />}
            </>
          )}
        </div>
      )}
    </DetailCard>
  );
}

function PocRow({ poc, rank }: { poc: POC; rank: string }) {
  const trust = contactTrustDisplay(poc.contact_trust_status);
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
          {rank}
        </span>
        <span className={`badge ${trust.className}`} title={`Contact trust ${poc.contact_trust_score}%`}>
          Contact Trust: {trust.label} · {poc.contact_trust_score}%
        </span>
      </div>
      <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-slate-100">
        {poc.full_name}
      </p>
      {poc.job_title && <p className="text-sm text-slate-600 dark:text-slate-300">{poc.job_title}</p>}
      <dl className="mt-3 grid grid-cols-2 gap-3">
        <Field label="Work Email">{poc.business_email || 'Not Publicly Available'}</Field>
        <Field label="Business Phone">{poc.business_phone || 'Not Publicly Available'}</Field>
        <Field label="LinkedIn">
          <ExternalLinkValue href={poc.professional_network_url} stripScheme />
        </Field>
        <Field label="GitHub">
          <ExternalLinkValue href={poc.contact_source === 'GitHub' ? poc.source_url : null} stripScheme />
        </Field>
        <Field label="Employment">
          {poc.employment_status ? poc.employment_status.replace(/_/g, ' ') : '—'}
        </Field>
        <Field label="Source">{poc.contact_source || '—'}</Field>
        <Field label="Last Verified">{formatDateTime(poc.last_verified_at)}</Field>
      </dl>
    </div>
  );
}

function RoleRecommendations({ roles }: { roles: RecommendedRole[] }) {
  const primary = roles.find((r) => r.is_primary) ?? roles[0];
  return (
    <div className="mt-2 rounded-lg border border-slate-100 dark:border-slate-800 p-3">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
        Recommended POC Role
      </p>
      <p className="mt-1 text-sm font-semibold text-slate-800 dark:text-slate-200">{primary.role}</p>
      {primary.reason && (
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{primary.reason}</p>
      )}
      {roles.length > 1 && (
        <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
          Also consider: {roles.slice(1, 4).map((r) => r.role).join(' · ')}
        </p>
      )}
    </div>
  );
}
