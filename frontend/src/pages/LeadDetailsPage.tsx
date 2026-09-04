import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ExternalLink, Trash2 } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card } from '@/components/ui/Card';
import { Badge, PriorityBadge } from '@/components/ui/Badge';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { ScoreIndicator } from '@/components/common/ScoreIndicator';
import { DetailCard, Field } from '@/components/leads/detail/DetailCard';
import { PitchBlock } from '@/components/leads/detail/PitchBlock';
import { StatusControl } from '@/components/leads/detail/StatusControl';
import { useDeleteLead, useLead } from '@/hooks/useLeads';
import { formatCurrency, formatDate, formatDateTime, formatScore } from '@/utils/format';
import type { ApiErrorShape } from '@/services/api';

function Chips({ items }: { items: string[] }) {
  if (items.length === 0) return <>—</>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <Badge key={item}>{item}</Badge>
      ))}
    </div>
  );
}

function ExternalLinkValue({ href }: { href: string | null }) {
  if (!href) return <>—</>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-brand-600 hover:underline"
    >
      <span className="truncate">{href}</span>
      <ExternalLink className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
    </a>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true" data-testid="lead-detail-skeleton">
      <div className="h-20 w-full animate-pulse rounded-xl bg-slate-100" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-40 w-full animate-pulse rounded-xl bg-slate-100" />
        ))}
      </div>
    </div>
  );
}

export function LeadDetailsPage() {
  const { id } = useParams();
  const leadId = Number(id);
  const validId = Number.isFinite(leadId);
  const navigate = useNavigate();

  const query = useLead(leadId);
  const deleteMutation = useDeleteLead();

  const notFound =
    !validId ||
    (query.isError && (query.error as unknown as ApiErrorShape | undefined)?.status === 404);

  const handleDelete = () => {
    if (!window.confirm('Delete this lead? This cannot be undone.')) return;
    deleteMutation.mutate(leadId, { onSuccess: () => navigate('/leads') });
  };

  const backLink = (
    <Link to="/leads" className="btn-ghost text-sm">
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
              <Link to="/leads" className="btn-primary">
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
      {/* Summary header */}
      <Card>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <PriorityBadge priority={lead.lead_priority} />
            <p className="mt-2 text-sm text-slate-500">
              {[lead.industry, lead.location].filter(Boolean).join(' · ') || 'No company details'}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <div className="text-right">
              <p className="text-xs uppercase tracking-wide text-slate-400">Lead score</p>
              <p className="text-2xl font-semibold tabular-nums text-slate-900">
                {formatScore(lead.lead_score)}
                <span className="text-sm font-normal text-slate-400"> / 100</span>
              </p>
            </div>
            <ScoreIndicator score={lead.lead_score} />
            <StatusControl leadId={lead.id} status={lead.status} />
            <button
              type="button"
              className="btn-secondary text-sm text-rose-600"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              Delete
            </button>
          </div>
        </div>
      </Card>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DetailCard title="Opportunity">
          <dl className="space-y-3">
            <Field label="Summary">{lead.opportunity_summary}</Field>
            <Field label="Recommended action">{lead.recommended_action}</Field>
          </dl>
        </DetailCard>

        <DetailCard title="Signal">
          <dl className="grid grid-cols-2 gap-3">
            <Field label="Type">{lead.signal_type ? <Badge>{lead.signal_type}</Badge> : undefined}</Field>
            <Field label="Detected">{formatDate(lead.signal_date)}</Field>
            <div className="col-span-2">
              <Field label="Title">{lead.signal_title}</Field>
            </div>
            <div className="col-span-2">
              <Field label="Description">{lead.signal_description}</Field>
            </div>
            <Field label="Confidence">
              {lead.signal_confidence != null ? `${Math.round(lead.signal_confidence)} / 100` : undefined}
            </Field>
            <Field label="Source">{lead.source_name}</Field>
            <div className="col-span-2">
              <Field label="Source URL">
                <ExternalLinkValue href={lead.source_url} />
              </Field>
            </div>
          </dl>
        </DetailCard>

        <DetailCard title="Technologies & Hiring">
          <dl className="space-y-3">
            <Field label="Technologies">
              <Chips items={lead.technologies} />
            </Field>
            <Field label="Hiring roles">
              <Chips items={lead.hiring_roles} />
            </Field>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Est. hiring">{lead.estimated_hiring ?? undefined}</Field>
              <Field label="Project">{lead.project_name}</Field>
              <Field label="Project value">{formatCurrency(lead.project_value)}</Field>
            </div>
          </dl>
        </DetailCard>

        <DetailCard title="Point of Contact">
          <dl className="grid grid-cols-2 gap-3">
            <Field label="Name">{lead.poc_name}</Field>
            <Field label="Title">{lead.poc_title}</Field>
            <div className="col-span-2">
              <Field label="LinkedIn">
                <ExternalLinkValue href={lead.poc_linkedin_url} />
              </Field>
            </div>
            <div className="col-span-2">
              <Field label="Public contact">{lead.public_contact}</Field>
            </div>
          </dl>
        </DetailCard>

        {lead.recommended_pitch && (
          <div className="lg:col-span-2">
            <DetailCard title="Recommended Pitch">
              <PitchBlock pitch={lead.recommended_pitch} />
            </DetailCard>
          </div>
        )}

        <div className="lg:col-span-2">
          <DetailCard title="Company & Metadata">
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Field label="Company size">{lead.company_size}</Field>
              <div className="col-span-2 sm:col-span-1">
                <Field label="Website">
                  <ExternalLinkValue href={lead.company_website} />
                </Field>
              </div>
              <Field label="Created">{formatDateTime(lead.created_at)}</Field>
              <Field label="Updated">{formatDateTime(lead.updated_at)}</Field>
              <Field label="Last verified">{formatDateTime(lead.last_verified_at)}</Field>
            </dl>
          </DetailCard>
        </div>
      </div>
    </PageContainer>
  );
}
