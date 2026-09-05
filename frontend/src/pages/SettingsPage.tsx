import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Check, RefreshCw } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Select } from '@/components/ui/Select';
import { SettingRow, SettingsSection } from '@/components/settings/SettingsSection';
import { usePreferences } from '@/hooks/usePreferences';
import { useHealth } from '@/hooks/useHealth';
import { API_BASE_URL } from '@/services/api';
import { PAGE_SIZE_OPTIONS } from '@/constants/leads';

function ConnectionDot({ label, tone }: { label: string; tone: 'ok' | 'bad' | 'idle' }) {
  const color = tone === 'ok' ? 'bg-emerald-500' : tone === 'bad' ? 'bg-rose-500' : 'bg-slate-300';
  return (
    <span className="inline-flex items-center gap-2 text-sm font-medium text-slate-700">
      <span className={`h-2.5 w-2.5 rounded-full ${color}`} aria-hidden="true" />
      {label}
    </span>
  );
}

export function SettingsPage() {
  const { prefs, update, reset } = usePreferences();
  const health = useHealth();
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
              <code className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-700">{API_BASE_URL}</code>
            }
          />
          <SettingRow
            label="Environment"
            control={<span className="text-sm text-slate-700">{health.data?.environment ?? 'Not available'}</span>}
          />
        </SettingsSection>

        <SettingsSection title="About" description="Application information.">
          <SettingRow
            label="Application"
            control={<span className="text-sm text-slate-700">{health.data?.app ?? 'LeadGenerationAgent'}</span>}
          />
          <SettingRow
            label="Version"
            control={<span className="text-sm text-slate-700">{health.data?.version ?? 'Not available'}</span>}
          />
          <SettingRow
            label="Accounts"
            hint="Authentication and multi-user accounts are not part of this phase."
            control={<span className="text-sm text-slate-500">Local, single user</span>}
          />
        </SettingsSection>
      </div>
    </PageContainer>
  );
}
