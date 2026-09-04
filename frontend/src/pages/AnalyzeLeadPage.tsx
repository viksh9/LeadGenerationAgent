import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { ErrorState } from '@/components/ui/States';
import { AnalyzeForm } from '@/components/leads/analyze/AnalyzeForm';
import { AnalysisResult } from '@/components/leads/analyze/AnalysisResult';
import { useAnalyzeLead } from '@/hooks/useLeads';
import type { ApiErrorShape } from '@/services/api';

export function AnalyzeLeadPage() {
  const mutation = useAnalyzeLead();

  const backLink = (
    <Link to="/leads" className="btn-ghost text-sm">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />
      Back to leads
    </Link>
  );

  const error = mutation.error as unknown as ApiErrorShape | undefined;

  return (
    <PageContainer
      title="Analyze a Lead"
      subtitle="Turn a raw business signal into a scored, prioritized opportunity."
      actions={backLink}
    >
      {mutation.data ? (
        <AnalysisResult result={mutation.data} onReset={() => mutation.reset()} />
      ) : (
        <div className="space-y-4">
          {mutation.isError && (
            <ErrorState
              message={error?.message ?? 'Unable to analyze this lead. Please check the fields and try again.'}
            />
          )}
          <AnalyzeForm onAnalyze={(payload) => mutation.mutate(payload)} isSubmitting={mutation.isPending} />
        </div>
      )}
    </PageContainer>
  );
}
