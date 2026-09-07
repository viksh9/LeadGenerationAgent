import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  fetchAlerts,
  fetchPreferences,
  fetchUnreadCount,
  setAlertStatus,
  updatePreferences,
} from '@/services/alerts';
import { useToast } from '@/contexts/ToastContext';
import type { ApiErrorShape } from '@/services/api';
import type {
  AlertListParams,
  AlertStatus,
  NotificationPreferenceUpdate,
} from '@/services/alerts';

const errText = (e: unknown, fallback: string) =>
  (e as ApiErrorShape | undefined)?.message ?? fallback;

/** Centralized query keys for the alert layer. */
export const alertKeys = {
  all: ['alerts'] as const,
  lists: () => [...alertKeys.all, 'list'] as const,
  list: (params: AlertListParams) => [...alertKeys.lists(), params] as const,
  unread: () => [...alertKeys.all, 'unread'] as const,
  preferences: ['notification-preferences'] as const,
};

/** Recent alerts, optionally filtered by status. */
export function useAlerts(params: AlertListParams = {}) {
  return useQuery({
    queryKey: alertKeys.list(params),
    queryFn: ({ signal }) => fetchAlerts(params, signal),
    placeholderData: keepPreviousData,
  });
}

/**
 * Unread alert count for the header bell badge. Polled every 60s so a running
 * backend surfaces new alerts without a manual refresh.
 */
export function useUnreadCount() {
  return useQuery({
    queryKey: alertKeys.unread(),
    queryFn: ({ signal }) => fetchUnreadCount(signal),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

// Any status change can move an alert in/out of the "unread" set, so invalidate
// both the lists and the unread count.
export function useSetAlertStatus() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: ({ id, status }: { id: number; status: AlertStatus }) => setAlertStatus(id, status),
    onSuccess: (_data, { status }) => {
      qc.invalidateQueries({ queryKey: alertKeys.all });
      qc.invalidateQueries({ queryKey: alertKeys.unread() });
      const verb =
        status === 'ACKNOWLEDGED'
          ? 'Alert acknowledged.'
          : status === 'DISMISSED'
            ? 'Alert dismissed.'
            : status === 'RESOLVED'
              ? 'Alert resolved.'
              : 'Alert reopened.';
      toast.success(verb);
    },
    onError: (e) => toast.error(errText(e, 'Unable to update the alert.')),
  });
}

/** Current notification preferences (server-owned). */
export function useNotificationPreferences() {
  return useQuery({
    queryKey: alertKeys.preferences,
    queryFn: ({ signal }) => fetchPreferences(signal),
  });
}

export function useUpdateNotificationPreferences() {
  const qc = useQueryClient();
  const toast = useToast();
  return useMutation({
    mutationFn: (payload: NotificationPreferenceUpdate) => updatePreferences(payload),
    onSuccess: (data) => {
      qc.setQueryData(alertKeys.preferences, data);
      toast.success('Notification preferences saved.');
    },
    onError: (e) => toast.error(errText(e, 'Unable to save notification preferences.')),
  });
}
