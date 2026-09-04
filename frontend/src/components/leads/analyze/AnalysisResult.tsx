import { Link } from 'react-router-dom';
import { CheckCircle2 } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Badge, PriorityBadge } from '@/components/ui/Badge';
import { ScoreIndicator } from '@/components/common/ScoreIndicator';
import { DetailCard, Field } from '@/components/leads/detail/DetailCard';
import { PitchBlock } from '@/components/leads/detail/PitchBlock';
import { Button } from '@/components/ui/Button';
import type { LeadAnalysis } from '@/types/lead';

export function AnalysisResult({ result, onReset }: { result: LeadAnalysis; onReset: () => void }) {
  const { signal_analysis, opportunity_analysis, poc_recommendation, pitch_result } = result;

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="h-6 w-6 shrink-0 text-emerald-500" aria-hidden="true" />
            <div>
              <p className="text-sm text-slate-500">
                {result.already_existed ? 'Re-analyzed existing lead' : 'Analysis complete'}
              </p>
              <p className="text-lg font-semibold text-slate-900">{result.company_name}</p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <PriorityBadge priority={result.priority} />
            <ScoreIndicator score={result.final_score} />
            <div className="flex gap-2">
              {result.lead_id != null && (
                <Link to={`/leads/${result.lead_id}`} className="btn-primary">
                  View full lead
                </Link>
              )}
              <Button variant="secondary" onClick={onReset}>
                Analyze another
              </Button>
            </div>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DetailCard title="Signals & Opportunity">
          <dl className="space-y-3">
            <Field label="Signals detected">
              <div className="flex flex-wrap gap-1.5">
                {signal_analysis.signal_types.map((type) => (
                  <Badge key={type}>{type}</Badge>
                ))}
              </div>
            </Field>
            <Field label="Opportunity">{opportunity_analysis.opportunity_type}</Field>
            <Field label="Staffing need">{opportunity_analysis.potential_staffing_need}</Field>
            <Field label="Business reason">{opportunity_analysis.business_reason}</Field>
            <Field label="Recommended action">{result.recommended_action}</Field>
          </dl>
        </DetailCard>

        <DetailCard title="Recommended Contact">
          <dl className="space-y-3">
            <Field label="Primary role">
              {poc_recommendation.primary_role ? (
                <span className="font-medium text-slate-900">{poc_recommendation.primary_role.role}</span>
              ) : undefined}
            </Field>
            <Field label="Secondary roles">
              {poc_recommendation.secondary_roles.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {poc_recommendation.secondary_roles.map((role) => (
                    <Badge key={role.role}>{role.role}</Badge>
                  ))}
                </div>
              ) : undefined}
            </Field>
            <Field label="Confidence">
              {`${poc_recommendation.recommendation_confidence} (${poc_recommendation.recommendation_confidence_label})`}
            </Field>
          </dl>
        </DetailCard>
      </div>

      <DetailCard title="Recommended Pitch">
        <p className="mb-2 text-sm font-medium text-slate-700">{pitch_result.email_subject}</p>
        <PitchBlock pitch={pitch_result.recommended_pitch} />
      </DetailCard>
    </div>
  );
}
