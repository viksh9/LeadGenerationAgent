import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { AnalyzeForm } from '@/components/leads/analyze/AnalyzeForm';
import { AnalyzingState } from '@/components/leads/analyze/AnalyzingState';
import { AnalysisResult } from '@/components/leads/analyze/AnalysisResult';
import { useAnalyzeLead } from '@/hooks/useLeads';

export function AnalyzeLeadPage() {
  const mutation = useAnalyzeLead();

  const backLink = (
    <Link to="/leads" className="btn-ghost text-sm">
      <ArrowLeft className="h-4 w-4" aria-hidden="true" />
      Back to leads
    </Link>
  );

  return (
    <PageContainer
      title="Analyze a Lead"
      subtitle="Turn a raw business signal into a scored, prioritized opportunity."
      actions={backLink}
    >
      {mutation.data ? (
        <AnalysisResult result={mutation.data} onReset={() => mutation.reset()} />
      ) : (
        // On failure the form stays mounted (entered data preserved) and the
        // error surfaces as a toast; re-submitting the form is "Try Again".
        <div className="space-y-4">
          <AnalyzeForm onAnalyze={(payload) => mutation.mutate(payload)} isSubmitting={mutation.isPending} />
          {mutation.isPending && <AnalyzingState />}
        </div>
      )}
    </PageContainer>
  );
}
