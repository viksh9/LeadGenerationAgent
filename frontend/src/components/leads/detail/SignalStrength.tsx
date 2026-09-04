/**
 * Signal strength derived from the persisted `signal_confidence` (0–100). This
 * is a presentation band of an existing backend value — not a new computation.
 * Shows both a label and the number so meaning never depends on colour alone.
 */
type Band = { label: 'STRONG' | 'MEDIUM' | 'WEAK'; className: string };

function band(value: number): Band {
  if (value >= 75) return { label: 'STRONG', className: 'bg-emerald-50 text-emerald-700 ring-emerald-200' };
  if (value >= 50) return { label: 'MEDIUM', className: 'bg-amber-50 text-amber-700 ring-amber-200' };
  return { label: 'WEAK', className: 'bg-slate-100 text-slate-600 ring-slate-200' };
}

export function SignalStrength({ confidence }: { confidence: number | null | undefined }) {
  if (confidence === null || confidence === undefined) {
    return <span className="text-sm text-slate-400">Not available</span>;
  }
  const value = Math.round(confidence);
  const { label, className } = band(value);
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`badge ring-1 ring-inset ${className}`}>{label}</span>
      <span className="text-sm font-semibold tabular-nums text-slate-700">
        {value}
        <span className="font-normal text-slate-400"> / 100</span>
      </span>
    </span>
  );
}
