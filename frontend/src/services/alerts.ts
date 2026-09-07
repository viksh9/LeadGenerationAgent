import { api } from './api';

/**
 * Thin API client + display helpers for the continuous-monitoring alert layer.
 *
 * Every alert is derived from real collected data and evidence — an alert only
 * exists because the backend detected a genuine change (a new high-intent lead,
 * a source failure, a closing tender…). No alerts are fabricated.
 */

export type AlertSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
export type AlertStatus = 'NEW' | 'ACKNOWLEDGED' | 'DISMISSED' | 'RESOLVED';

/** The set of alert kinds the backend can raise. */
export type AlertType =
  | 'NEW_HIGH_INTENT_LEAD'
  | 'LEAD_SCORE_INCREASED'
  | 'LEAD_PRIORITY_INCREASED'
  | 'HIRING_SURGE'
  | 'NEW_PROJECT'
  | 'NEW_TENDER'
  | 'TENDER_CLOSING_SOON'
  | 'NEW_TECHNOLOGY_SIGNAL'
  | 'NEW_DECISION_MAKER'
  | 'CONTACT_VERIFIED'
  | 'EVIDENCE_CONFLICT'
  | 'EVIDENCE_STALE'
  | 'SOURCE_FAILURE'
  | 'SOURCE_RECOVERED';

export interface Alert {
  id: number;
  alert_type: string;
  severity: AlertSeverity;
  status: AlertStatus;
  title: string;
  message?: string | null;
  company_id?: number | null;
  lead_id?: number | null;
  opportunity_id?: number | null;
  signal_id?: number | null;
  tender_id?: number | null;
  source_id?: string | null;
  evidence_ids: number[];
  link?: string | null;
  triggered_at: string;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
}

export interface AlertList {
  items: Alert[];
  total: number;
  unread_count: number;
}

export interface UnreadCount {
  unread_count: number;
}

export interface AlertListParams {
  status?: AlertStatus;
  limit?: number;
  offset?: number;
}

export interface NotificationPreference {
  hot_leads_only: boolean;
  min_score_increase: number;
  enabled_alert_types: string[];
  min_severity: AlertSeverity;
  channels: string[];
}

export type NotificationPreferenceUpdate = Partial<NotificationPreference>;

/** Recent alerts, optionally filtered by status (GET /alerts). */
export async function fetchAlerts(
  params: AlertListParams = {},
  signal?: AbortSignal,
): Promise<AlertList> {
  const { data } = await api.get<AlertList>('/alerts', { params, signal });
  return data;
}

/** Just the unread count — cheap enough to poll for the header bell badge. */
export async function fetchUnreadCount(signal?: AbortSignal): Promise<UnreadCount> {
  const { data } = await api.get<UnreadCount>('/alerts/unread-count', { signal });
  return data;
}

/** A single alert (GET /alerts/{id}). */
export async function fetchAlert(id: number, signal?: AbortSignal): Promise<Alert> {
  const { data } = await api.get<Alert>(`/alerts/${id}`, { signal });
  return data;
}

/** Transition an alert's status (acknowledge / dismiss / resolve / reopen). */
export async function setAlertStatus(id: number, status: AlertStatus): Promise<Alert> {
  const { data } = await api.post<Alert>(`/alerts/${id}/status`, { status });
  return data;
}

/** Current notification preferences (GET /notification-preferences). */
export async function fetchPreferences(signal?: AbortSignal): Promise<NotificationPreference> {
  const { data } = await api.get<NotificationPreference>('/notification-preferences', { signal });
  return data;
}

/** Persist a partial change to the notification preferences. */
export async function updatePreferences(
  payload: NotificationPreferenceUpdate,
): Promise<NotificationPreference> {
  const { data } = await api.put<NotificationPreference>('/notification-preferences', payload);
  return data;
}

export interface AlertDisplay {
  label: string;
  className: string;
}

const EMERALD = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
const BLUE = 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300';
const AMBER = 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300';
const ROSE = 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300';
const SLATE = 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';

const SEVERITY_DISPLAY: Record<AlertSeverity, AlertDisplay> = {
  CRITICAL: { label: 'Critical', className: ROSE },
  HIGH: { label: 'High', className: AMBER },
  MEDIUM: { label: 'Medium', className: BLUE },
  LOW: { label: 'Low', className: SLATE },
};

/** Display label + honest Tailwind badge classes for an alert severity. */
export function alertSeverityDisplay(severity: AlertSeverity): AlertDisplay {
  return SEVERITY_DISPLAY[severity] ?? { label: severity, className: SLATE };
}

const STATUS_DISPLAY: Record<AlertStatus, AlertDisplay> = {
  NEW: { label: 'New', className: BLUE },
  ACKNOWLEDGED: { label: 'Acknowledged', className: AMBER },
  RESOLVED: { label: 'Resolved', className: EMERALD },
  DISMISSED: { label: 'Dismissed', className: SLATE },
};

/** Display label + honest Tailwind badge classes for an alert status. */
export function alertStatusDisplay(status: AlertStatus): AlertDisplay {
  return STATUS_DISPLAY[status] ?? { label: status, className: SLATE };
}

const ALERT_TYPE_LABELS: Record<string, string> = {
  NEW_HIGH_INTENT_LEAD: 'New high-intent lead',
  LEAD_SCORE_INCREASED: 'Lead score increased',
  LEAD_PRIORITY_INCREASED: 'Lead priority increased',
  HIRING_SURGE: 'Hiring surge',
  NEW_PROJECT: 'New project',
  NEW_TENDER: 'New tender',
  TENDER_CLOSING_SOON: 'Tender closing soon',
  NEW_TECHNOLOGY_SIGNAL: 'New technology signal',
  NEW_DECISION_MAKER: 'New decision maker',
  CONTACT_VERIFIED: 'Contact verified',
  EVIDENCE_CONFLICT: 'Evidence conflict',
  EVIDENCE_STALE: 'Stale evidence',
  SOURCE_FAILURE: 'Source failure',
  SOURCE_RECOVERED: 'Source recovered',
};

/** Human-readable label for an alert type (falls back to a Title-Cased enum). */
export function alertTypeLabel(type: string): string {
  return (
    ALERT_TYPE_LABELS[type] ??
    type
      .toLowerCase()
      .split('_')
      .map((word) => (word ? word[0].toUpperCase() + word.slice(1) : word))
      .join(' ')
  );
}

/** Every selectable alert type, for the notification-preferences checklist. */
export const ALERT_TYPES: string[] = Object.keys(ALERT_TYPE_LABELS);
