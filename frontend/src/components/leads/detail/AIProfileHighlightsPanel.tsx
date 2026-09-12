import { useState } from 'react';
import { Sparkles, ShieldCheck, RefreshCw, FileSearch } from 'lucide-react';
import { DetailCard, Field } from '@/components/leads/detail/DetailCard';
import { EvidenceDrawer } from '@/components/leads/detail/EvidenceDrawer';
import { useLeadIntelligence, useRefreshLeadIntelligence } from '@/hooks/useLeadIntelligence';
import { pocStatusDisplay, trustLevelDisplay, freshnessDisplay } from '@/services/intelligence';

/**
 * AI Profile Highlights (§31). Shows deterministic, evidence-grounded highlights
 * (always, from real data) plus the AI insight when available — otherwise
 * "AI Profile Highlights unavailable" (never fabricated prose, §42). Surfaces Data
 * Trust and Contact Trust distinctly (never merged with lead score, §33) with a
 * "View Evidence" trigger, and only badges the sources that actually contributed.
 */
export function AIProfileHighlightsPanel({ leadId }: { leadId: number }) {
  const intel = useLeadIntelligence(leadId);
  const refresh = useRefreshLeadIntelligence(leadId);
  const [drawer, setDrawer] = useState(false);

  if (intel.isLoading) {
    return <DetailCard title="AI Profile Highlights"><p className="text-sm text-slate-500 dark:text-slate-400">Loading intelligence…</p></DetailCard>;
  }
  if (intel.isError || !intel.data) {
    return <DetailCard title="AI Profile Highlights"><p className="text-sm text-rose-600 dark:text-rose-400">Unable to load intelligence.</p></DetailCard>;
  }

  const d = intel.data;
  const hl = d.ai_highlights;
  const fresh = freshnessDisplay(d.freshness_status);
  const sourceLabels = Array.from(new Set(d.sources.map((s) => s.source))).slice(0, 12);

  return (
    <>
      <DetailCard title="AI Profile Highlights">
        {/* Trust row — Data Trust and Contact Trust kept distinct (§32/§33). */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="badge bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300" title="Quality of company/opportunity evidence">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" /> Data Trust {d.data_trust}%
          </span>
          <span className="badge bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300" title="Reliability of the contact match (separate from lead score)">
            Contact Trust {d.contact_trust}%
          </span>
          <span className={`badge ${fresh.className}`}>Freshness: {fresh.label}</span>
          <div className="ml-auto flex items-center gap-2">
            <button type="button" className="btn-ghost text-sm" onClick={() => setDrawer(true)}>
              <FileSearch className="h-4 w-4" aria-hidden="true" /> View Evidence
            </button>
            <button type="button" className="btn-ghost text-sm" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
              <RefreshCw className={refresh.isPending ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
              {refresh.isPending ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        </div>

        {/* Structured highlights (deterministic, real data). */}
        <dl className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {hl.highlights
            .filter((h) => h.highlight_title !== 'AI Insight')
            .map((h) => {
              const t = trustLevelDisplay(h.trust_level);
              return (
                <div key={h.highlight_title}>
                  <dt className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
                    {h.highlight_title}
                    <span className={`badge ${t.className}`}>{t.label}</span>
                  </dt>
                  <dd className="mt-0.5 break-words text-sm text-slate-800 dark:text-slate-200">{h.highlight_text}</dd>
                </div>
              );
            })}
        </dl>

        {/* AI insight — the only AI-authored line. */}
        <div className="mt-4 rounded-lg border border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40 p-3">
          <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" /> AI Insight
            {hl.ai_available && hl.model_version && (
              <span className="ml-1 normal-case text-slate-400 dark:text-slate-500">· {hl.model_version}</span>
            )}
          </p>
          {hl.ai_available && hl.ai_insight ? (
            <p className="mt-1 text-sm text-slate-800 dark:text-slate-200">{hl.ai_insight}</p>
          ) : (
            <p className="mt-1 text-sm italic text-slate-500 dark:text-slate-400">AI Profile Highlights unavailable.</p>
          )}
        </div>

        {/* Recommended sales action + contributing source badges (§29/§34). */}
        <div className="mt-4 space-y-3">
          <Field label="Recommended action">{d.sales_action}</Field>
          {d.primary_poc && (
            <Field label="Primary POC">
              {d.primary_poc.poc.full_name}
              {d.primary_poc.poc.job_title ? ` — ${d.primary_poc.poc.job_title}` : ''}{' '}
              <span className={`badge ${pocStatusDisplay(d.primary_poc.poc_status).className}`}>
                {pocStatusDisplay(d.primary_poc.poc_status).label}
              </span>
            </Field>
          )}
          <div>
            <dt className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">Sources</dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">
              {sourceLabels.length === 0 ? (
                <span className="text-sm text-slate-400 dark:text-slate-500">Source Unavailable</span>
              ) : (
                sourceLabels.map((s) => (
                  <span key={s} className="badge bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300">
                    {s}
                  </span>
                ))
              )}
            </dd>
          </div>
        </div>
      </DetailCard>

      <EvidenceDrawer leadId={leadId} open={drawer} onClose={() => setDrawer(false)} />
    </>
  );
}
