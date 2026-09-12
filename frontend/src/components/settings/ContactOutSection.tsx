import { RefreshCw, Plug } from 'lucide-react';
import { SettingRow, SettingsSection } from '@/components/settings/SettingsSection';
import { useContactOutStatus, useTestContactOut } from '@/hooks/useContactOut';
import { contactOutStatusDisplay } from '@/services/contactOut';

/**
 * ContactOut integration status card. Shows Configured / Not Configured (config
 * state, never the token) and offers a real, credit-free connection test. A live
 * CONNECTED result only appears after actually contacting ContactOut.
 */
export function ContactOutSection() {
  const status = useContactOutStatus();
  const test = useTestContactOut();

  return (
    <SettingsSection
      title="ContactOut integration"
      description="Real POC / decision-maker discovery and contact enrichment. The API token is read from the environment and is never displayed."
      headerRight={
        status.data?.configured ? (
          <button
            type="button"
            className="btn-secondary text-sm"
            onClick={() => test.mutate()}
            disabled={test.isPending}
          >
            <Plug className={test.isPending ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
            {test.isPending ? 'Testing…' : 'Test connection'}
          </button>
        ) : undefined
      }
    >
      {status.isLoading ? (
        <p className="py-2.5 text-sm text-slate-500 dark:text-slate-400">Checking ContactOut…</p>
      ) : status.isError ? (
        <div className="flex items-center justify-between gap-3 py-2.5">
          <p className="text-sm text-rose-600 dark:text-rose-400">Unable to load ContactOut status.</p>
          <button type="button" className="btn-ghost text-sm" onClick={() => status.refetch()}>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Retry
          </button>
        </div>
      ) : status.data ? (
        <>
          <SettingRow
            label="Status"
            control={
              <span className={`badge ${contactOutStatusDisplay(status.data.status).className}`}>
                {contactOutStatusDisplay(status.data.status).label}
              </span>
            }
          />
          {test.data && (
            <SettingRow
              label="Last connection test"
              control={
                <span className={`badge ${contactOutStatusDisplay(test.data.connection_status).className}`}>
                  {contactOutStatusDisplay(test.data.connection_status).label}
                </span>
              }
            />
          )}
          <SettingRow
            label="Credit controls"
            hint="Conservative, configurable caps per opportunity."
            control={
              <span className="text-sm text-slate-700 dark:text-slate-300">
                {status.data.max_poc_searches_per_opportunity} searches · {status.data.max_enrichments_per_opportunity} enrichments
              </span>
            }
          />
          <SettingRow
            label="Cache window"
            hint="Recent verified POCs are reused instead of spending a credit."
            control={
              <span className="text-sm text-slate-700 dark:text-slate-300">
                {status.data.cache_ttl_hours} h
              </span>
            }
          />
          {status.data.note && (
            <p className="border-t border-slate-100 dark:border-slate-800 pt-3 text-xs text-slate-500 dark:text-slate-400">
              {status.data.note}
            </p>
          )}
        </>
      ) : (
        <p className="py-2.5 text-sm text-slate-500 dark:text-slate-400">ContactOut status unavailable.</p>
      )}
    </SettingsSection>
  );
}
