import type { LeadPriority } from '@/types/lead';

/** Tailwind badge classes per lead priority (restrained, accessible contrast). */
export const priorityBadgeClass: Record<LeadPriority, string> = {
  HOT: 'bg-rose-50 text-rose-700 ring-1 ring-inset ring-rose-200',
  WARM: 'bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-200',
  NURTURE: 'bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-200',
  LOW: 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 ring-1 ring-inset ring-slate-200 dark:ring-slate-700',
};

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return '—';
  return Math.round(score).toString();
}

export function formatCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** Priority band a raw 0-100 score falls into (mirrors the backend thresholds). */
export function scoreBand(score: number): LeadPriority {
  if (score >= 80) return 'HOT';
  if (score >= 60) return 'WARM';
  if (score >= 40) return 'NURTURE';
  return 'LOW';
}

/** Chart colours per priority (restrained; align with the priority badges). */
export const priorityColor: Record<LeadPriority, string> = {
  HOT: '#e11d48',
  WARM: '#d97706',
  NURTURE: '#2563eb',
  LOW: '#64748b',
};

/** Relative "time ago" label from an ISO timestamp. */
export function timeAgo(value: string | null | undefined): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  const diffMs = Date.now() - date.getTime();
  const day = 86_400_000;
  if (diffMs < 0) return formatDate(value);
  if (diffMs < day && new Date().toDateString() === date.toDateString()) return 'Today';
  if (diffMs < 2 * day) return 'Yesterday';
  const days = Math.floor(diffMs / day);
  if (days < 30) return `${days} days ago`;
  return formatDate(value);
}
