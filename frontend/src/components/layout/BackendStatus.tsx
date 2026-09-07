import { useHealth } from '@/hooks/useHealth';

/** Unobtrusive backend connectivity indicator (uses GET /health; not polled). */
export function BackendStatus() {
  const { isLoading, isError } = useHealth();
  const { label, dot } = isLoading
    ? { label: 'Checking…', dot: 'bg-slate-300 dark:bg-slate-600' }
    : isError
      ? { label: 'Unavailable', dot: 'bg-rose-500' }
      : { label: 'Connected', dot: 'bg-emerald-500' };

  return (
    <span className="inline-flex items-center gap-2 text-xs text-slate-400 dark:text-slate-500">
      <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden="true" />
      Backend: {label}
    </span>
  );
}
