import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Check, RefreshCw } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Select } from '@/components/ui/Select';
import { SettingRow, SettingsSection } from '@/components/settings/SettingsSection';
import { usePreferences } from '@/hooks/usePreferences';
import { useThemeContext } from '@/contexts/ThemeContext';
import { useHealth } from '@/hooks/useHealth';
import { useSources } from '@/hooks/useSources';
import { useAiStatus } from '@/hooks/useAi';
import { aiProviderStatusDisplay } from '@/services/ai';
import type { ThemePreference } from '@/types/settings';
import { API_BASE_URL } from '@/services/api';
import { PAGE_SIZE_OPTIONS } from '@/constants/leads';
import { sourceStatusDisplay, connectionStatusDisplay } from '@/services/sources';
import { formatDateTime } from '@/utils/format';

function ConnectionDot({ label, tone }: { label: string; tone: 'ok' | 'bad' | 'idle' }) {
  const color = tone === 'ok' ? 'bg-emerald-500' : tone === 'bad' ? 'bg-rose-500' : 'bg-slate-300 dark:bg-slate-600';
  return (
    <span className="inline-flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300">
      <span className={`h-2.5 w-2.5 rounded-full ${color}`} aria-hidden="true" />
      {label}
    </span>
  );
}

export function SettingsPage() {
  const { prefs, update, reset } = usePreferences();
  const { theme, setTheme } = useThemeContext();
  const health = useHealth();
  const sources = useSources();
  const aiStatus = useAiStatus();
  const queryClient = useQueryClient();
  const [cacheCleared, setCacheCleared] = useState(false);

  const clearCache = () => {
    queryClient.clear();
    setCacheCleared(true);
    setTimeout(() => setCacheCleared(false), 1500);
    health.refetch();
  };

  const status = health.isLoading
    ? { tone: 'idle' as const, label: 'Checking…' }
    : health.isError
      ? { tone: 'bad' as const, label: 'Unreachable' }
      : { tone: 'ok' as const, label: 'Connected' };

  return (
    <PageContainer title="Settings" subtitle="Preferences, connection, and application information.">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SettingsSection
          title="Preferences"
          description="Saved in this browser only — there is no account yet."
        >
          <SettingRow
            label="Theme"
            hint="System follows your device appearance."
            control={
              <Select
                aria-label="Theme"
                className="w-32"
                value={theme}
                onChange={(e) => setTheme(e.target.value as ThemePreference)}
              >
                <option value="system">System</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </Select>
            }
          />
          <SettingRow
            label="Leads per page"
            hint="Applied as the default page size on the Leads list."
            control={
              <Select
                aria-label="Leads per page"
                className="w-28"
                value={prefs.leadsPageSize}
                onChange={(e) => update('leadsPageSize', Number(e.target.value))}
              >
                {PAGE_SIZE_OPTIONS.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </Select>
            }
          />
          <SettingRow
            label="Reset preferences"
            hint="Restore the default browser preferences."
            control={
              <button type="button" className="btn-secondary text-sm" onClick={reset}>
                Reset
              </button>
            }
          />
        </SettingsSection>

        <SettingsSection
          title="Data & cache"
          description="Manage locally cached data fetched from the backend."
        >
          <SettingRow
            label="Clear cached data"
            hint="Clears in-memory query caches and refetches. Does not delete backend data."
            control={
              <button type="button" className="btn-secondary text-sm" onClick={clearCache}>
                {cacheCleared ? (
                  <>
                    <Check className="h-4 w-4 text-emerald-500" aria-hidden="true" />
                    Cleared
                  </>
                ) : (
                  'Clear cache'
                )}
              </button>
            }
          />
        </SettingsSection>

        <SettingsSection
          title="Connection"
          description="Backend the app is talking to."
        >
          <SettingRow
            label="Status"
            control={
              <div className="flex items-center gap-3">
                <ConnectionDot label={status.label} tone={status.tone} />
                <button
                  type="button"
                  className="btn-ghost text-sm"
                  onClick={() => health.refetch()}
                  disabled={health.isFetching}
                  aria-label="Test connection"
                >
                  <RefreshCw
                    className={health.isFetching ? 'h-4 w-4 animate-spin' : 'h-4 w-4'}
                    aria-hidden="true"
                  />
                  Test
                </button>
              </div>
            }
          />
          <SettingRow
            label="API base URL"
            control={
              <code className="rounded bg-slate-100 dark:bg-slate-800 px-2 py-1 text-xs text-slate-700 dark:text-slate-300">{API_BASE_URL}</code>
            }
          />
          <SettingRow
            label="Environment"
            control={<span className="text-sm text-slate-700 dark:text-slate-300">{health.data?.environment ?? 'Not available'}</span>}
          />
        </SettingsSection>

        <SettingsSection title="About" description="Application information.">
          <SettingRow
            label="Application"
            control={<span className="text-sm text-slate-700 dark:text-slate-300">{health.data?.app ?? 'LeadGenerationAgent'}</span>}
          />
          <SettingRow
            label="Version"
            control={<span className="text-sm text-slate-700 dark:text-slate-300">{health.data?.version ?? 'Not available'}</span>}
          />
          <SettingRow
            label="Accounts"
            hint="Authentication and multi-user accounts are not part of this phase."
            control={<span className="text-sm text-slate-500 dark:text-slate-400">Local, single user</span>}
          />
        </SettingsSection>

        <SettingsSection
          title="AI provider"
          description="AI intelligence is grounded on real data. When no provider is configured, a deterministic baseline is used instead of fabricated content."
        >
          {aiStatus.isLoading ? (
            <p className="py-2.5 text-sm text-slate-500 dark:text-slate-400">Checking AI provider…</p>
          ) : aiStatus.isError ? (
            <div className="flex items-center justify-between gap-3 py-2.5">
              <p className="text-sm text-rose-600 dark:text-rose-400">Unable to load AI provider status.</p>
              <button type="button" className="btn-ghost text-sm" onClick={() => aiStatus.refetch()}>
                <RefreshCw className="h-4 w-4" aria-hidden="true" />
                Retry
              </button>
            </div>
          ) : aiStatus.data ? (
            <>
              <SettingRow
                label="Status"
                control={
                  <span className={`badge ${aiProviderStatusDisplay(aiStatus.data.status).className}`}>
                    {aiProviderStatusDisplay(aiStatus.data.status).label}
                  </span>
                }
              />
              <SettingRow
                label="Provider"
                control={
                  <span className="text-sm text-slate-700 dark:text-slate-300">
                    {aiStatus.data.provider ?? 'None'}
                  </span>
                }
              />
              <SettingRow
                label="Model"
                control={
                  <span className="text-sm text-slate-700 dark:text-slate-300">
                    {aiStatus.data.model ?? 'Not configured'}
                  </span>
                }
              />
              <SettingRow
                label="Deterministic baseline"
                hint="Honest rule-derived analysis used when no LLM is available."
                control={
                  <span className="text-sm text-slate-700 dark:text-slate-300">
                    {aiStatus.data.deterministic_baseline_available ? 'Available' : 'Unavailable'}
                  </span>
                }
              />
              {aiStatus.data.note && (
                <p className="border-t border-slate-100 dark:border-slate-800 pt-3 text-xs text-slate-500 dark:text-slate-400">
                  {aiStatus.data.note}
                </p>
              )}
            </>
          ) : (
            <p className="py-2.5 text-sm text-slate-500 dark:text-slate-400">AI provider status unavailable.</p>
          )}
        </SettingsSection>

        <div className="lg:col-span-2">
          <SettingsSection
            title="Data sources"
            description="Source connectivity reflects real configuration. A source is only 'Connected' after a verified live check."
            headerRight={
              sources.data?.data_mode ? (
                <span className="badge bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  Data mode: {sources.data.data_mode}
                </span>
              ) : undefined
            }
          >
            {sources.isLoading ? (
              <p className="py-2.5 text-sm text-slate-500 dark:text-slate-400">Checking source connectivity…</p>
            ) : sources.isError ? (
              <div className="flex items-center justify-between gap-3 py-2.5">
                <p className="text-sm text-rose-600 dark:text-rose-400">Unable to load source connectivity.</p>
                <button type="button" className="btn-ghost text-sm" onClick={() => sources.refetch()}>
                  <RefreshCw className="h-4 w-4" aria-hidden="true" />
                  Retry
                </button>
              </div>
            ) : !sources.data || sources.data.items.length === 0 ? (
              <p className="py-2.5 text-sm text-slate-500 dark:text-slate-400">No data sources are registered.</p>
            ) : (
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {sources.data.items.map((source) => {
                  const display = sourceStatusDisplay(source.status);
                  const connection = source.connection_status
                    ? connectionStatusDisplay(source.connection_status)
                    : null;
                  return (
                    <li key={source.source_id} className="flex items-start justify-between gap-3 py-2.5">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-800 dark:text-slate-200">{source.name}</p>
                        <p className="text-xs text-slate-400 dark:text-slate-500">{source.category}</p>
                        {source.detail && (
                          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{source.detail}</p>
                        )}
                        {source.capabilities.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {source.capabilities.map((capability) => (
                              <span
                                key={capability}
                                className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                              >
                                {capability}
                              </span>
                            ))}
                          </div>
                        )}
                        <div className="mt-1.5 space-y-0.5 text-xs text-slate-500 dark:text-slate-400">
                          {connection ? (
                            <p className="flex items-center gap-1.5">
                              <span>Connectivity:</span>
                              <span className={`badge ${connection.className}`}>{connection.label}</span>
                            </p>
                          ) : (
                            <p className="text-slate-400 dark:text-slate-500">Not yet checked</p>
                          )}
                          {source.last_checked_at && (
                            <p>Last checked: {formatDateTime(source.last_checked_at)}</p>
                          )}
                          {source.last_success_at && (
                            <p>Last successful: {formatDateTime(source.last_success_at)}</p>
                          )}
                          {source.last_error && (
                            <p className="text-rose-600 dark:text-rose-400">Last error: {source.last_error}</p>
                          )}
                          {source.last_ingestion_at ? (
                            <>
                              <p>Last ingestion: {formatDateTime(source.last_ingestion_at)}</p>
                              <p>
                                Records: {source.last_ingestion_records_fetched ?? 0} fetched ·{' '}
                                {source.last_ingestion_records_persisted ?? 0} new
                              </p>
                            </>
                          ) : (
                            <p className="text-slate-400 dark:text-slate-500">Not yet ingested</p>
                          )}
                        </div>
                      </div>
                      <span className={`badge shrink-0 ${display.className}`}>{display.label}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </SettingsSection>
        </div>
      </div>
    </PageContainer>
  );
}
