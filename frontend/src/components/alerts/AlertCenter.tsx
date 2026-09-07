import { useEffect, useId, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Bell, Check, X } from 'lucide-react';
import { cn } from '@/utils/cn';
import { relativeTime } from '@/utils/format';
import { alertTypeLabel } from '@/services/alerts';
import { useAlerts, useSetAlertStatus, useUnreadCount } from '@/hooks/useAlerts';
import { SeverityBadge } from '@/components/alerts/badges';
import { LoadingState, ErrorState, EmptyState } from '@/components/ui/States';
import type { Alert } from '@/services/alerts';

/** Short context line describing what a given alert is attached to. */
function alertContext(alert: Alert): string | null {
  if (alert.company_id) return `Company #${alert.company_id}`;
  if (alert.lead_id) return `Lead #${alert.lead_id}`;
  if (alert.opportunity_id) return `Opportunity #${alert.opportunity_id}`;
  if (alert.tender_id) return `Tender #${alert.tender_id}`;
  if (alert.signal_id) return `Signal #${alert.signal_id}`;
  if (alert.source_id) return `Source: ${alert.source_id}`;
  return null;
}

function AlertRow({ alert, onNavigate }: { alert: Alert; onNavigate: () => void }) {
  const setStatus = useSetAlertStatus();
  const context = alertContext(alert);
  const isUnread = alert.status === 'NEW';

  return (
    <li
      className={cn(
        'flex gap-3 px-4 py-3',
        isUnread && 'bg-brand-50/60 dark:bg-brand-500/5',
      )}
    >
      {isUnread ? (
        <span
          className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-500"
          aria-label="Unread"
        />
      ) : (
        <span className="mt-1.5 h-2 w-2 shrink-0" aria-hidden="true" />
      )}
      <div className="min-w-0 flex-1">
        <Link
          to={alert.link ?? '/monitoring'}
          onClick={onNavigate}
          className="block rounded focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <div className="flex items-center gap-2">
            <SeverityBadge severity={alert.severity} />
            <span className="truncate text-xs font-medium text-slate-500 dark:text-slate-400">
              {alertTypeLabel(alert.alert_type)}
            </span>
          </div>
          <p className="mt-1 text-sm font-medium text-slate-900 dark:text-slate-100">
            {alert.title}
          </p>
          {alert.message && (
            <p className="mt-0.5 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">
              {alert.message}
            </p>
          )}
          <div className="mt-1 flex items-center gap-2 text-xs text-slate-400 dark:text-slate-500">
            <span>{relativeTime(alert.triggered_at)}</span>
            {context && (
              <>
                <span aria-hidden="true">·</span>
                <span className="truncate">{context}</span>
              </>
            )}
          </div>
        </Link>
        {isUnread && (
          <div className="mt-2 flex items-center gap-2">
            <button
              type="button"
              className="btn-ghost text-xs"
              disabled={setStatus.isPending}
              onClick={() => setStatus.mutate({ id: alert.id, status: 'ACKNOWLEDGED' })}
            >
              <Check className="h-3.5 w-3.5" aria-hidden="true" />
              Acknowledge
            </button>
            <button
              type="button"
              className="btn-ghost text-xs"
              disabled={setStatus.isPending}
              onClick={() => setStatus.mutate({ id: alert.id, status: 'DISMISSED' })}
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
              Dismiss
            </button>
          </div>
        )}
      </div>
    </li>
  );
}

/**
 * Header bell + dropdown alert panel. The bell shows the live unread count
 * (polled) and opens a scrollable list of recent alerts, each linking through
 * to its subject and offering acknowledge / dismiss actions.
 */
export function AlertCenter() {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const location = useLocation();

  const unread = useUnreadCount();
  const alerts = useAlerts({ limit: 20 });
  const setStatus = useSetAlertStatus();

  const unreadCount = unread.data?.unread_count ?? 0;
  const items = alerts.data?.items ?? [];
  const unreadItems = items.filter((a) => a.status === 'NEW');

  // Close when the route changes (navigating to a linked alert).
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  // Close on outside click and on Escape.
  useEffect(() => {
    if (!open) return;
    const onPointer = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const markAllRead = () => {
    unreadItems.forEach((a) => setStatus.mutate({ id: a.id, status: 'ACKNOWLEDGED' }));
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        className="btn-ghost relative"
        aria-label="Notifications"
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((prev) => !prev)}
      >
        <Bell className="h-5 w-5" />
        {unreadCount > 0 && (
          <span
            className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold leading-none text-white"
            aria-label={`${unreadCount} unread alerts`}
          >
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          id={panelId}
          role="dialog"
          aria-label="Alert center"
          className="absolute right-0 z-40 mt-2 flex max-h-[32rem] w-96 max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-900"
        >
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Alerts</h2>
              {unreadCount > 0 && (
                <span className="badge bg-brand-100 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300">
                  {unreadCount} unread
                </span>
              )}
            </div>
            {unreadItems.length > 0 && (
              <button
                type="button"
                className="btn-ghost text-xs"
                disabled={setStatus.isPending}
                onClick={markAllRead}
              >
                Mark all read
              </button>
            )}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto">
            {alerts.isLoading ? (
              <LoadingState message="Loading alerts…" />
            ) : alerts.isError ? (
              <ErrorState message="Unable to load alerts." onRetry={() => alerts.refetch()} />
            ) : items.length === 0 ? (
              <EmptyState title="No alerts" description="New monitoring alerts will appear here." />
            ) : (
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {items.map((alert) => (
                  <AlertRow key={alert.id} alert={alert} onNavigate={() => setOpen(false)} />
                ))}
              </ul>
            )}
          </div>

          <div className="border-t border-slate-200 px-4 py-2.5 text-center dark:border-slate-800">
            <Link
              to="/monitoring"
              onClick={() => setOpen(false)}
              className="text-xs font-medium text-brand-600 hover:underline dark:text-brand-400"
            >
              View monitoring dashboard
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
