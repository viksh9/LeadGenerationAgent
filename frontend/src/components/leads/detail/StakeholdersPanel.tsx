import { DetailCard } from '@/components/leads/detail/DetailCard';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import { useLeadStakeholders } from '@/hooks/useLeadStakeholders';
import {
  outreachReadinessDisplay,
  verificationDisplay,
  type DecisionMaker,
  type StakeholderRole,
} from '@/services/decisionMakers';
import { cn } from '@/utils/cn';
import { formatScore } from '@/utils/format';

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
      {children}
    </p>
  );
}

function RoleRow({ role }: { role: StakeholderRole }) {
  return (
    <li
      className={cn(
        'rounded-lg border px-3 py-2',
        role.is_primary
          ? 'border-brand-100 bg-brand-50 dark:border-brand-500/30 dark:bg-brand-500/10'
          : 'border-slate-200 dark:border-slate-800',
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-slate-900 dark:text-slate-100">{role.role}</span>
        {role.is_primary && (
          <span className="badge bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-300">
            Primary
          </span>
        )}
        <span className="badge bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          {role.role_category}
        </span>
        <span className="ml-auto text-xs text-slate-500 dark:text-slate-400">
          Relevance {formatScore(role.relevance_score)}
        </span>
      </div>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
        {role.reason ?? 'No reason recorded.'}
      </p>
    </li>
  );
}

/** A real person / contact row — never fabricates a name, email, or source. */
function PersonRow({ person }: { person: DecisionMaker }) {
  const v = verificationDisplay(person.verification_status);
  const identity = person.full_name ?? person.business_email ?? 'Contact not identified yet';
  const muted = !person.full_name && !person.business_email;
  return (
    <li className="rounded-lg border border-slate-200 dark:border-slate-800 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            'text-sm font-medium',
            muted ? 'text-slate-400 dark:text-slate-500' : 'text-slate-900 dark:text-slate-100',
          )}
        >
          {identity}
        </span>
        <span className={cn('badge', v.className)}>{v.label}</span>
      </div>
      {person.job_title && (
        <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-300">{person.job_title}</p>
      )}
      <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
        {person.full_name && person.business_email && <span>{person.business_email}</span>}
        <span>Evidence {formatScore(person.evidence_confidence)}</span>
        {person.source_url ? (
          <ExternalLinkValue href={person.source_url} label={person.contact_source ?? 'Source'} />
        ) : (
          person.contact_source && <span>{person.contact_source}</span>
        )}
      </div>
    </li>
  );
}

/**
 * Stakeholder intelligence for a lead (GET /leads/{id}/stakeholders). Keeps three
 * distinct concepts separate and honest:
 *   - Recommended ROLES (not people),
 *   - Verified decision makers (real people, with verification status),
 *   - Business contacts (real, source-backed).
 * Plus an outreach-readiness signal. Nothing here is fabricated.
 */
export function StakeholdersPanel({ leadId }: { leadId: number }) {
  const { data, isLoading, isError, refetch } = useLeadStakeholders(leadId);

  return (
    <DetailCard title="Stakeholders">
      {isLoading && <p className="text-sm text-slate-500 dark:text-slate-400">Loading stakeholders…</p>}
      {isError && (
        <div className="text-sm">
          <p className="text-rose-600">Unable to load stakeholders.</p>
          <button type="button" className="btn-ghost mt-1 text-sm" onClick={() => refetch()}>
            Try again
          </button>
        </div>
      )}
      {data && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
              Outreach readiness
            </span>
            <span className={cn('badge', outreachReadinessDisplay(data.outreach_readiness).className)}>
              {outreachReadinessDisplay(data.outreach_readiness).label}
            </span>
          </div>
          {data.outreach_reasons.length > 0 && (
            <ul className="-mt-3 list-disc space-y-0.5 pl-5 text-xs text-slate-500 dark:text-slate-400">
              {data.outreach_reasons.map((reason, i) => (
                <li key={i}>{reason}</li>
              ))}
            </ul>
          )}

          <div>
            <SectionHeading>Recommended roles</SectionHeading>
            {data.recommended_roles.length > 0 ? (
              <ul className="space-y-2">
                {data.recommended_roles.map((role, i) => (
                  <RoleRow key={`${role.role}-${i}`} role={role} />
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-400 dark:text-slate-500">No recommended roles yet.</p>
            )}
          </div>

          <div>
            <SectionHeading>Verified decision makers</SectionHeading>
            {data.verified_decision_makers.length > 0 ? (
              <ul className="space-y-2">
                {data.verified_decision_makers.map((p) => (
                  <PersonRow key={p.id} person={p} />
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-400 dark:text-slate-500">No verified people yet.</p>
            )}
          </div>

          <div>
            <SectionHeading>Business contacts</SectionHeading>
            {data.business_contacts.length > 0 ? (
              <ul className="space-y-2">
                {data.business_contacts.map((p) => (
                  <PersonRow key={p.id} person={p} />
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate-400 dark:text-slate-500">
                No source-backed business contacts yet.
              </p>
            )}
          </div>
        </div>
      )}
    </DetailCard>
  );
}
