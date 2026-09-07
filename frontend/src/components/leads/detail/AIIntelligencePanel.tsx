import { AlertTriangle, Sparkles } from 'lucide-react';
import { DetailCard } from '@/components/leads/detail/DetailCard';
import { useLeadAI } from '@/hooks/useAi';
import { analysisStatusDisplay, type AIClaim } from '@/services/ai';

/** Evidence id chips, e.g. "evidence #123". Renders nothing when empty. */
function EvidenceRefs({ ids }: { ids: number[] }) {
  if (!ids || ids.length === 0) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {ids.map((id) => (
        <span
          key={id}
          className="rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
        >
          evidence #{id}
        </span>
      ))}
    </div>
  );
}

/**
 * A verified FACT — source-backed. Emerald styling + explicit "Fact" label so it
 * is never confused with reasoning.
 */
function FactItem({ claim }: { claim: AIClaim }) {
  return (
    <li className="rounded-md border border-emerald-200 bg-emerald-50/60 px-3 py-2 dark:border-emerald-500/30 dark:bg-emerald-500/10">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 shrink-0 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300">
          Fact
        </span>
        <p className="text-sm text-slate-800 dark:text-slate-100">{claim.claim_text}</p>
      </div>
      <EvidenceRefs ids={claim.evidence_ids} />
    </li>
  );
}

/**
 * An INFERENCE — reasoning, not confirmed fact. Amber/muted styling + explicit
 * "Inference" label. Never rendered as a fact.
 */
function InferenceItem({ claim }: { claim: AIClaim }) {
  return (
    <li className="rounded-md border border-amber-200 bg-amber-50/50 px-3 py-2 dark:border-amber-500/30 dark:bg-amber-500/10">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-800 dark:bg-amber-500/20 dark:text-amber-300">
          Inference
        </span>
        <p className="text-sm text-slate-700 dark:text-slate-200">{claim.claim_text}</p>
      </div>
      {claim.evidence_ids.length > 0 && (
        <p className="mt-1 text-[11px] text-amber-700/80 dark:text-amber-300/80">
          Reasoning informed by evidence {claim.evidence_ids.map((id) => `#${id}`).join(', ')}
        </p>
      )}
    </li>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {title}
      </p>
      {children}
    </div>
  );
}

export function AIIntelligencePanel({ lead }: { lead: { id: number } }) {
  const { data: ai, isLoading, isError, refetch } = useLeadAI(lead.id);

  return (
    <DetailCard title="AI Intelligence">
      {isLoading && (
        <p className="text-sm text-slate-500 dark:text-slate-400">Loading AI analysis…</p>
      )}
      {isError && (
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-rose-600 dark:text-rose-400">Unable to load AI analysis.</p>
          <button type="button" className="btn-ghost text-sm" onClick={() => refetch()}>
            Retry
          </button>
        </div>
      )}
      {ai && (
        <div className="space-y-4">
          {/* Provenance: LLM vs deterministic baseline, status, and reasoning confidence. */}
          {(() => {
            const status = analysisStatusDisplay(ai.analysis_status);
            return (
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1 text-sm font-medium text-slate-700 dark:text-slate-200">
                  <Sparkles className="h-4 w-4 text-brand-500" aria-hidden="true" />
                  {ai.ai_generated
                    ? `AI: ${ai.model_name ?? ai.provider ?? 'model'}`
                    : 'Deterministic baseline'}
                </span>
                <span className={`badge ${status.className}`}>{status.label}</span>
                <span
                  className="badge bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                  title="How confident the AI reasoning is — separate from the lead score."
                >
                  AI reasoning confidence: {Math.round(ai.confidence)}%
                </span>
              </div>
            );
          })()}
          <p className="text-xs text-slate-400 dark:text-slate-500">
            AI reasoning confidence reflects the strength of this analysis only. It is separate from
            the lead score.
          </p>

          {ai.unsupported_claim_count > 0 && (
            <p className="flex items-center gap-1.5 rounded-md bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {ai.unsupported_claim_count} claim(s) flagged as unsupported.
            </p>
          )}

          {ai.executive_summary && (
            <Section title="Executive summary">
              <p className="text-sm text-slate-700 dark:text-slate-200">{ai.executive_summary}</p>
            </Section>
          )}

          {ai.verified_facts.length > 0 && (
            <Section title="Verified facts">
              <ul className="space-y-2">
                {ai.verified_facts.map((claim, i) => (
                  <FactItem key={`fact-${i}`} claim={claim} />
                ))}
              </ul>
            </Section>
          )}

          {ai.inferred_insights.length > 0 && (
            <Section title="Inferred insights">
              <ul className="space-y-2">
                {ai.inferred_insights.map((claim, i) => (
                  <InferenceItem key={`inf-${i}`} claim={claim} />
                ))}
              </ul>
            </Section>
          )}

          {ai.unknowns.length > 0 && (
            <Section title="Unknowns">
              <ul className="list-disc space-y-1 pl-5 text-sm text-slate-500 dark:text-slate-400">
                {ai.unknowns.map((u, i) => (
                  <li key={`unk-${i}`}>{u}</li>
                ))}
              </ul>
            </Section>
          )}

          {ai.opportunity_explanation && (
            <Section title="Why this opportunity">
              <p className="text-sm text-slate-700 dark:text-slate-200">
                {ai.opportunity_explanation}
              </p>
            </Section>
          )}

          {ai.next_best_action && (
            <Section title="Next best action">
              <p className="text-sm text-slate-700 dark:text-slate-200">{ai.next_best_action}</p>
            </Section>
          )}

          {ai.sales_angle && (
            <Section title="Sales angle">
              <p className="text-sm text-slate-700 dark:text-slate-200">{ai.sales_angle}</p>
            </Section>
          )}

          {ai.risk_flags.length > 0 && (
            <Section title="Risk flags">
              <ul className="space-y-1 text-sm text-rose-700 dark:text-rose-300">
                {ai.risk_flags.map((r, i) => (
                  <li key={`risk-${i}`} className="flex items-start gap-1.5">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {ai.verified_facts.length === 0 &&
            ai.inferred_insights.length === 0 &&
            ai.unknowns.length === 0 &&
            !ai.executive_summary && (
              <p className="text-sm text-slate-500 dark:text-slate-400">
                No AI analysis is available for this lead yet.
              </p>
            )}
        </div>
      )}
    </DetailCard>
  );
}
