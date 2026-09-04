import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Building2, ExternalLink, Users } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';
import { Badge, PriorityBadge } from '@/components/ui/Badge';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { CompanySignalsTable } from '@/components/companies/CompanySignalsTable';
import { useCompany } from '@/hooks/useCompanies';

function StatCard({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="card card-pad">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <div className="mt-1 text-lg font-semibold text-slate-900">{children}</div>
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true" data-testid="company-skeleton">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-20 animate-pulse rounded-xl bg-slate-100" />
        ))}
      </div>
      <div className="h-64 animate-pulse rounded-xl bg-slate-100" />
    </div>
  );
}

export function CompanyDetailsPage() {
  const { name: rawName } = useParams();
  const name = rawName ? decodeURIComponent(rawName) : '';
  const { company, isLoading, isError, refetch, notFound } = useCompany(name);

  const backLink = (
    <Link to="/companies" className="btn-ghost text-sm">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />
      Back to companies
    </Link>
  );

  if (isLoading) {
    return (
      <PageContainer title={name} subtitle="Loading company profile…" actions={backLink}>
        <DetailSkeleton />
      </PageContainer>
    );
  }

  if (isError) {
    return (
      <PageContainer title={name} subtitle="Company profile" actions={backLink}>
        <Card>
          <ErrorState message="Unable to load this company." onRetry={() => refetch()} />
        </Card>
      </PageContainer>
    );
  }

  if (notFound || !company) {
    return (
      <PageContainer title={name || 'Company'} subtitle="Company profile" actions={backLink}>
        <Card>
          <EmptyState
            title="Company not found"
            description="No leads were found for this company. It may have been removed."
            action={
              <Link to="/companies" className="btn-secondary">
                Back to companies
              </Link>
            }
          />
        </Card>
      </PageContainer>
    );
  }

  const subtitle = [company.industry, company.location].filter(Boolean).join(' • ') || 'Company profile';

  return (
    <PageContainer
      title={company.name}
      subtitle={subtitle}
      actions={
        <div className="flex items-center gap-2">
          {backLink}
          <Link
            to={`/leads?search=${encodeURIComponent(company.name)}`}
            className="btn-secondary text-sm"
          >
            View all leads
          </Link>
        </div>
      }
    >
      <div className="space-y-6">
        {/* KPIs */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatCard label="Leads">
            <span className="tabular-nums">{company.leadCount}</span>
          </StatCard>
          <StatCard label="Best score">
            <span className="tabular-nums">
              {Math.round(company.bestScore)}
              <span className="text-sm font-normal text-slate-400"> / 100</span>
            </span>
          </StatCard>
          <StatCard label="Top priority">
            <PriorityBadge priority={company.topPriority} />
          </StatCard>
          <StatCard label="Est. hiring">
            <span className="tabular-nums">{company.estimatedHiring || '—'}</span>
          </StatCard>
        </div>

        {/* Profile */}
        <Card>
          <div className="card-pad">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Building2 className="h-4 w-4 text-slate-400" aria-hidden="true" />
              Company profile
            </h3>
            <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-3 sm:grid-cols-2">
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Industry</dt>
                <dd className="text-sm text-slate-800">{company.industry ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Location</dt>
                <dd className="text-sm text-slate-800">{company.location ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Company size</dt>
                <dd className="text-sm text-slate-800">{company.companySize ?? '—'}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-slate-500">Website</dt>
                <dd className="text-sm text-slate-800">
                  {company.website ? (
                    <a
                      href={company.website}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex items-center gap-1 text-brand-600 hover:text-brand-700"
                    >
                      {company.website.replace(/^https?:\/\//, '')}
                      <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                    </a>
                  ) : (
                    '—'
                  )}
                </dd>
              </div>
            </dl>

            <div className="mt-4">
              <dt className="text-xs uppercase tracking-wide text-slate-500">Technology stack</dt>
              <dd className="mt-1 flex flex-wrap gap-1">
                {company.technologies.length === 0 ? (
                  <span className="text-sm text-slate-400">—</span>
                ) : (
                  company.technologies.map((tech) => <Badge key={tech}>{tech}</Badge>)
                )}
              </dd>
            </div>
          </div>
        </Card>

        {/* Signals / opportunities */}
        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-900">
            Signals &amp; opportunities ({company.leadCount})
          </h3>
          <Card padded={false}>
            <CompanySignalsTable leads={company.leads} />
          </Card>
        </div>

        {/* Key contacts */}
        {company.contacts.length > 0 && (
          <div>
            <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Users className="h-4 w-4 text-slate-400" aria-hidden="true" />
              Key contacts
            </h3>
            <Card>
              <ul className="divide-y divide-slate-100">
                {company.contacts.map((contact) => (
                  <li key={contact.name} className="flex items-center justify-between px-5 py-3">
                    <div>
                      <p className="text-sm font-medium text-slate-900">{contact.name}</p>
                      {contact.title && <p className="text-xs text-slate-500">{contact.title}</p>}
                    </div>
                    {contact.linkedinUrl && (
                      <a
                        href={contact.linkedinUrl}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="inline-flex items-center gap-1 text-sm text-brand-600 hover:text-brand-700"
                      >
                        LinkedIn
                        <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        )}
      </div>
    </PageContainer>
  );
}
