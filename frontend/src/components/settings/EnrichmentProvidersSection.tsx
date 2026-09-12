import { RefreshCw, Plug } from 'lucide-react';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useEnrichmentStatus, useTestEnrichmentProvider } from '@/hooks/useEnrichmentProviders';
import {
  capabilityLabels,
  configStatusDisplay,
  providerLabel,
  testResultDisplay,
  type EnrichmentProviderStatus,
} from '@/services/enrichmentProviders';

/**
 * Multi-provider contact-enrichment status card (Prompt 49, §46). Lists every paid
 * provider (ContactOut, Apollo, Lusha, Prospeo, Hunter) with its configuration state
 * and declared capabilities. Each configured provider offers a real connectivity test
 * — a LIVE_VERIFIED result only appears after actually contacting the provider. API
 * keys are read from the environment and are never displayed.
 */
function ProviderRow({ provider }: { provider: EnrichmentProviderStatus }) {
  const test = useTestEnrichmentProvider();
  const cfg = configStatusDisplay(provider.status);
  const caps = capabilityLabels(provider.capabilities);
  const isConfigured = provider.status === 'CONFIGURED';

  return (
    <div className="flex flex-col gap-2 border-b border-slate-100 dark:border-slate-800 py-3 last:border-b-0">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-slate-800 dark:text-slate-200">
            {providerLabel(provider.provider)}
          </span>
          <span className={`badge ${cfg.className}`}>{cfg.label}</span>
          {test.data && test.variables === provider.provider && (
            <span className={`badge ${testResultDisplay(test.data.result).className}`}>
              {testResultDisplay(test.data.result).label}
            </span>
          )}
        </div>
        {isConfigured && (
          <button
            type="button"
            className="btn-secondary text-sm"
            onClick={() => test.mutate(provider.provider)}
            disabled={test.isPending}
          >
            <Plug className={test.isPending && test.variables === provider.provider ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
            {test.isPending && test.variables === provider.provider ? 'Testing…' : 'Test'}
          </button>
        )}
      </div>
      {caps.length > 0 && (
        <p className="text-xs text-slate-500 dark:text-slate-400">{caps.join(' · ')}</p>
      )}
    </div>
  );
}

export function EnrichmentProvidersSection() {
  const status = useEnrichmentStatus();

  return (
    <SettingsSection
      title="Contact enrichment providers"
      description="Paid providers used by the credit-aware enrichment waterfall. API keys are read from the environment and never displayed. Free/public sources (official website, GitHub, Wikidata, OpenCorporates) always run first."
      headerRight={
        status.isError ? (
          <button type="button" className="btn-ghost text-sm" onClick={() => status.refetch()}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Retry
          </button>
        ) : undefined
      }
    >
      {status.isLoading ? (
        <p className="py-2.5 text-sm text-slate-500 dark:text-slate-400">Checking providers…</p>
      ) : status.isError ? (
        <p className="py-2.5 text-sm text-rose-600 dark:text-rose-400">Unable to load enrichment provider status.</p>
      ) : status.data && status.data.providers.length > 0 ? (
        <div>
          {status.data.providers.map((p) => (
            <ProviderRow key={p.provider} provider={p} />
          ))}
        </div>
      ) : (
        <p className="py-2.5 text-sm text-slate-500 dark:text-slate-400">No enrichment providers registered.</p>
      )}
    </SettingsSection>
  );
}
