import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { CompanyHeader } from '@/components/companies/CompanyHeader';
import { CompanyIntelligencePanel } from '@/components/companies/CompanyIntelligencePanel';
import { OfficialCompanyPanel } from '@/components/companies/OfficialCompanyPanel';
import { CompanyOverview } from '@/components/companies/CompanyOverview';
import { AccountOpportunitySummary } from '@/components/companies/AccountOpportunitySummary';
import { TechnologyLandscape } from '@/components/companies/TechnologyLandscape';
import { SignalTimeline } from '@/components/companies/SignalTimeline';
import { BusinessTimeline } from '@/components/companies/BusinessTimeline';
import { HiringIntelligence } from '@/components/companies/HiringIntelligence';
import { ProjectIntelligence } from '@/components/companies/ProjectIntelligence';
import { CompanyOpportunities } from '@/components/companies/CompanyOpportunities';
import { DecisionMakerRecommendations } from '@/components/companies/DecisionMakerRecommendations';
import { RelatedLeads } from '@/components/companies/RelatedLeads';
import { CompanyEvidence } from '@/components/companies/CompanyEvidence';
import { CareerSources } from '@/components/companies/CareerSources';
import { AccountAction } from '@/components/companies/AccountAction';
import { useCompany } from '@/hooks/useCompanies';

function DetailSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true" data-testid="company-skeleton">
      <div className="h-24 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-40 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
          ))}
        </div>
        <div className="space-y-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-40 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
          ))}
        </div>
      </div>
    </div>
  );
}

export function CompanyDetailsPage() {
  const { name: rawName } = useParams();
  const name = rawName ? decodeURIComponent(rawName) : '';
  const { company, isLoading, isError, isFetching, refetch, notFound } = useCompany(name);

  const backLink = (
    <Link to="/companies" className="btn-ghost text-sm">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />
      Back to companies
    </Link>
  );

  if (isLoading) {
    return (
      <PageContainer title={name} subtitle="Loading account intelligence…" actions={backLink}>
        <DetailSkeleton />
      </PageContainer>
    );
  }

  if (isError) {
    return (
      <PageContainer title={name} subtitle="Company intelligence" actions={backLink}>
        <Card>
          <ErrorState message="Unable to load company intelligence." onRetry={() => refetch()} />
        </Card>
      </PageContainer>
    );
  }

  if (notFound || !company) {
    return (
      <PageContainer title={name || 'Company'} subtitle="Company intelligence" actions={backLink}>
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

  const subtitle =
    [company.industry, company.location].filter(Boolean).join(' • ') || 'Company intelligence';
  const noSignals = company.metrics.totalSignals === 0;

  return (
    <PageContainer
      title={company.name}
      subtitle={subtitle}
      actions={
        <div className="flex items-center gap-2">
          {backLink}
          <button
            type="button"
            className="btn-secondary text-sm"
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="Refresh account intelligence"
          >
            <RefreshCw className={isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
            Refresh
          </button>
          <Link
            to={`/leads?search=${encodeURIComponent(company.name)}`}
            className="btn-secondary text-sm"
          >
            View leads
          </Link>
        </div>
      }
    >
      <div className="space-y-4">
        <CompanyHeader company={company} />
        <CompanyIntelligencePanel name={company.name} />
        <OfficialCompanyPanel companyName={company.name} />

        {noSignals && (
          <Card>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              No meaningful business signals available yet. Additional project or hiring signals are
              needed before this account can be qualified.
            </p>
          </Card>
        )}

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* Main intelligence column */}
          <div className="space-y-4 lg:col-span-2">
            <AccountOpportunitySummary company={company} />
            <SignalTimeline company={company} />
            <BusinessTimeline company={company} />
            <TechnologyLandscape company={company} />
            <ProjectIntelligence company={company} />
            <CompanyOpportunities company={company} />
            <RelatedLeads company={company} />
            <CareerSources company={company} />
            <CompanyEvidence company={company} />
          </div>

          {/* Secondary rail */}
          <div className="space-y-4">
            <AccountAction company={company} />
            <CompanyOverview company={company} />
            <HiringIntelligence company={company} />
            <DecisionMakerRecommendations company={company} />
          </div>
        </div>
      </div>
    </PageContainer>
  );
}
