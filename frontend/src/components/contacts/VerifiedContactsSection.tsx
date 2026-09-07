import { Link } from 'react-router-dom';
import { Card } from '@/components/ui/Card';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import { useVerifiedContacts } from '@/hooks/useContactsApi';
import { verificationDisplay, type DecisionMaker } from '@/services/decisionMakers';
import { cn } from '@/utils/cn';
import { formatScore, formatDateTime } from '@/utils/format';

/** Primary identity for a row: the person's name, or — for contact-only rows —
 * the business email. Never fabricates a value. */
function primaryIdentity(c: DecisionMaker): { label: string; muted: boolean } {
  if (c.full_name) return { label: c.full_name, muted: false };
  if (c.business_email) return { label: c.business_email, muted: false };
  return { label: 'Contact not identified yet', muted: true };
}

function VerificationBadge({ status }: { status: string }) {
  const d = verificationDisplay(status);
  return <span className={cn('badge', d.className)}>{d.label}</span>;
}

/**
 * Real, backend-sourced people & business contacts (GET /contacts). This is the
 * verified-data section — distinct from the client-derived role recommendations
 * below it. Renders honest loading / empty / error states and never fabricates a
 * person, email, or source.
 */
export function VerifiedContactsSection() {
  const { data, isLoading, isError, refetch } = useVerifiedContacts({ people_only: false });

  return (
    <Card padded={false} data-testid="verified-contacts-section">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 dark:border-slate-800 px-5 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Verified people &amp; contacts
          </h2>
          <p className="text-xs text-slate-400 dark:text-slate-500">
            Real people and business contacts collected from sources by enrichment.
          </p>
        </div>
        {data && data.total > 0 && (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {data.total.toLocaleString()} record{data.total === 1 ? '' : 's'}
          </p>
        )}
      </div>

      <div className="px-5 py-4">
        {isLoading ? (
          <div className="space-y-2" aria-hidden="true" data-testid="verified-contacts-skeleton">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800" />
            ))}
          </div>
        ) : isError ? (
          <ErrorState message="Unable to load verified people & contacts." onRetry={() => refetch()} />
        ) : !data || data.items.length === 0 ? (
          <EmptyState
            title="No verified people or contacts yet"
            description="Run enrichment from a company page to collect real decision-makers and business contacts."
            action={
              <Link to="/companies" className="btn-secondary">
                View companies
              </Link>
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">
                  <th className="py-2 pr-3 font-medium">Person / contact</th>
                  <th className="py-2 pr-3 font-medium">Title</th>
                  <th className="py-2 pr-3 font-medium">Company</th>
                  <th className="py-2 pr-3 font-medium">Verification</th>
                  <th className="py-2 pr-3 font-medium">Source</th>
                  <th className="py-2 pr-3 font-medium">Evidence</th>
                  <th className="py-2 pr-3 font-medium">Freshness</th>
                  <th className="py-2 font-medium">Last verified</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {data.items.map((c) => {
                  const identity = primaryIdentity(c);
                  return (
                    <tr key={c.id} className="align-top">
                      <td className="py-2.5 pr-3">
                        <span
                          className={cn(
                            'block font-medium',
                            identity.muted
                              ? 'text-slate-400 dark:text-slate-500'
                              : 'text-slate-900 dark:text-slate-100',
                          )}
                        >
                          {identity.label}
                        </span>
                        {c.full_name && c.business_email && (
                          <span className="block text-xs text-slate-400 dark:text-slate-500">
                            {c.business_email}
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 pr-3 text-slate-700 dark:text-slate-300">{c.job_title ?? '—'}</td>
                      <td className="py-2.5 pr-3 text-slate-700 dark:text-slate-300">{c.company_name ?? '—'}</td>
                      <td className="py-2.5 pr-3">
                        <VerificationBadge status={c.verification_status} />
                      </td>
                      <td className="py-2.5 pr-3">
                        {c.source_url ? (
                          <ExternalLinkValue href={c.source_url} label={c.contact_source ?? 'Source'} />
                        ) : (
                          <span className="text-slate-400 dark:text-slate-500">
                            {c.contact_source ?? '—'}
                          </span>
                        )}
                      </td>
                      <td className="py-2.5 pr-3 text-slate-700 dark:text-slate-300">
                        {formatScore(c.evidence_confidence)}
                      </td>
                      <td className="py-2.5 pr-3 text-slate-700 dark:text-slate-300">
                        {formatScore(c.freshness_score)}
                      </td>
                      <td className="py-2.5 whitespace-nowrap text-slate-500 dark:text-slate-400">
                        {formatDateTime(c.last_verified_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Card>
  );
}
