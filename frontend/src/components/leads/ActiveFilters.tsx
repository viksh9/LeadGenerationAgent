import { X } from 'lucide-react';
import { humanizeSignal } from '@/constants/leads';
import type { LeadListParams } from '@/types/lead';

/** Filter keys that appear as removable chips (page/sort are not "filters"). */
type ChipKey =
  | 'search'
  | 'industry'
  | 'location'
  | 'signal_type'
  | 'lead_priority'
  | 'status'
  | 'min_score'
  | 'max_score'
  | 'technology';

interface ActiveFiltersProps {
  params: LeadListParams;
  onRemove: (key: ChipKey) => void;
  onClear: () => void;
}

function chipLabel(key: ChipKey, params: LeadListParams): string | null {
  const v = params[key];
  if (v === undefined || v === '' || v === null) return null;
  switch (key) {
    case 'search':
      return `Search: "${v}"`;
    case 'industry':
      return `Industry: ${v}`;
    case 'location':
      return `Location: ${v}`;
    case 'signal_type':
      return `Signal: ${humanizeSignal(params.signal_type)}`;
    case 'lead_priority':
      return `Priority: ${v}`;
    case 'status':
      return `Status: ${v}`;
    case 'min_score':
      return `Score ≥ ${v}`;
    case 'max_score':
      return `Score ≤ ${v}`;
    case 'technology':
      return `Tech: ${v}`;
    default:
      return null;
  }
}

const CHIP_ORDER: ChipKey[] = [
  'search',
  'industry',
  'location',
  'signal_type',
  'lead_priority',
  'status',
  'min_score',
  'max_score',
  'technology',
];

export function ActiveFilters({ params, onRemove, onClear }: ActiveFiltersProps) {
  const chips = CHIP_ORDER.map((key) => ({ key, label: chipLabel(key, params) })).filter(
    (c): c is { key: ChipKey; label: string } => c.label !== null,
  );

  if (chips.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2" aria-label="Active filters">
      {chips.map(({ key, label }) => (
        <span key={key} className="chip">
          {label}
          <button
            type="button"
            className="rounded-full p-0.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
            onClick={() => onRemove(key)}
            aria-label={`Remove filter ${label}`}
          >
            <X className="h-3 w-3" aria-hidden="true" />
          </button>
        </span>
      ))}
      <button type="button" className="text-xs font-medium text-brand-600 hover:text-brand-700" onClick={onClear}>
        Clear all
      </button>
    </div>
  );
}
