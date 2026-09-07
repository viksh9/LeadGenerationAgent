import { useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { LeadHeader } from '@/components/leads/detail/LeadHeader';
import { CompanySummaryCard } from '@/components/leads/detail/CompanySummaryCard';
import { SignalPanel } from '@/components/leads/detail/SignalPanel';
import { OpportunityPanel } from '@/components/leads/detail/OpportunityPanel';
import { TechnologyList } from '@/components/leads/detail/TechnologyList';
import { POCPanel } from '@/components/leads/detail/POCPanel';
import { StakeholdersPanel } from '@/components/leads/detail/StakeholdersPanel';
import { EvidencePanel } from '@/components/leads/detail/EvidencePanel';
import { VerificationPanel } from '@/components/leads/detail/VerificationPanel';
import { OutreachPanel } from '@/components/leads/detail/OutreachPanel';
import { RecommendationCard } from '@/components/leads/detail/RecommendationCard';
import { useDeleteLead, useLead } from '@/hooks/useLeads';
import type { ApiErrorShape } from '@/services/api';

function DetailSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true" data-testid="lead-detail-skeleton">
      <div className="h-24 w-full animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-40 w-full animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
          ))}
        </div>
        <div className="space-y-4">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="h-40 w-full animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" />
          ))}
        </div>
      </div>
    </div>
  );
}

export function LeadDetailsPage() {
  const { id } = useParams();
  const leadId = Number(id);
  const validId = Number.isFinite(leadId);
  const navigate = useNavigate();
  const location = useLocation();
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  // Preserve the leads list filters the user came from, when available.
  const leadsSearch = (location.state as { leadsSearch?: string } | null)?.leadsSearch ?? '';
  const leadsTo = `/leads${leadsSearch}`;

  const query = useLead(leadId);
  const deleteMutation = useDeleteLead();

  const notFound =
    !validId ||
    (query.isError && (query.error as unknown as ApiErrorShape | undefined)?.status === 404);

  const backLink = (
    <Link to={leadsTo} className="btn-ghost text-sm">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />
      Back to leads
    </Link>
  );

  if (notFound) {
    return (
      <PageContainer title="Lead" actions={backLink}>
        <Card>
          <EmptyState
            title="Lead not found"
            description="This lead may have been deleted or the link is incorrect."
            action={
              <Link to={leadsTo} className="btn-primary">
                Back to leads
              </Link>
            }
          />
        </Card>
      </PageContainer>
    );
  }

  if (query.isLoading) {
    return (
      <PageContainer title="Lead" actions={backLink}>
        <DetailSkeleton />
      </PageContainer>
    );
  }

  if (query.isError || !query.data) {
    return (
      <PageContainer title="Lead" actions={backLink}>
        <ErrorState message="Unable to load this lead." onRetry={() => query.refetch()} />
      </PageContainer>
    );
  }

  const lead = query.data;

  return (
    <PageContainer title={lead.company_name} actions={backLink}>
      <div className="space-y-4">
        <LeadHeader
          lead={lead}
          onRefresh={() => query.refetch()}
          refreshing={query.isFetching}
          onDelete={() => setConfirmingDelete(true)}
          deleting={deleteMutation.isPending}
        />

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* Main analysis */}
          <div className="space-y-4 lg:col-span-2">
            <OpportunityPanel lead={lead} />
            <SignalPanel lead={lead} />
            <TechnologyList lead={lead} />
            <CompanySummaryCard lead={lead} />
            <EvidencePanel lead={lead} />
            <VerificationPanel leadId={lead.id} />
            <OutreachPanel lead={lead} />
          </div>

          {/* Score / action / contact rail */}
          <div className="space-y-4">
            <RecommendationCard lead={lead} />
            <POCPanel lead={lead} />
            <StakeholdersPanel leadId={lead.id} />
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={confirmingDelete}
        destructive
        title="Delete lead?"
        description="This action cannot be undone."
        confirmLabel="Delete"
        busy={deleteMutation.isPending}
        onConfirm={() =>
          deleteMutation.mutate(leadId, {
            onSuccess: () => {
              setConfirmingDelete(false);
              navigate(leadsTo);
            },
          })
        }
        onCancel={() => setConfirmingDelete(false)}
      />
    </PageContainer>
  );
}
