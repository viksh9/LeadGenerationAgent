import { Search, X } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { PRIORITIES, SIGNAL_TYPES, STATUSES } from '@/constants/leads';
import type { LeadListParams } from '@/types/lead';

interface LeadsFiltersProps {
  params: LeadListParams;
  searchText: string;
  onSearchTextChange: (value: string) => void;
  onChange: (patch: Partial<LeadListParams>) => void;
  onClear: () => void;
  activeFilterCount: number;
}

/** Blank option value maps back to "no filter" (undefined). */
function toParam(value: string): string | undefined {
  return value === '' ? undefined : value;
}
function toNumber(value: string): number | undefined {
  if (value === '') return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

export function LeadsFilters({
  params,
  searchText,
  onSearchTextChange,
  onChange,
  onClear,
  activeFilterCount,
}: LeadsFiltersProps) {
  return (
    <div className="card card-pad">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="sm:col-span-2 lg:col-span-2">
          <label className="label" htmlFor="lead-search">
            Search
          </label>
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
              aria-hidden="true"
            />
            <input
              id="lead-search"
              className="input pl-9"
              placeholder="Company, signal, or project…"
              value={searchText}
              onChange={(e) => onSearchTextChange(e.target.value)}
            />
          </div>
        </div>

        <Select
          label="Priority"
          value={params.lead_priority ?? ''}
          onChange={(e) => onChange({ lead_priority: toParam(e.target.value) as LeadListParams['lead_priority'] })}
        >
          <option value="">All priorities</option>
          {PRIORITIES.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </Select>

        <Select
          label="Status"
          value={params.status ?? ''}
          onChange={(e) => onChange({ status: toParam(e.target.value) as LeadListParams['status'] })}
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>

        <Select
          label="Signal type"
          value={params.signal_type ?? ''}
          onChange={(e) => onChange({ signal_type: toParam(e.target.value) as LeadListParams['signal_type'] })}
        >
          <option value="">All signals</option>
          {SIGNAL_TYPES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>

        <Input
          label="Industry"
          placeholder="e.g. BFSI"
          value={params.industry ?? ''}
          onChange={(e) => onChange({ industry: toParam(e.target.value) })}
        />

        <Input
          label="Technology"
          placeholder="e.g. Java"
          value={params.technology ?? ''}
          onChange={(e) => onChange({ technology: toParam(e.target.value) })}
        />

        <Input
          label="Min score"
          type="number"
          min={0}
          max={100}
          value={params.min_score ?? ''}
          onChange={(e) => onChange({ min_score: toNumber(e.target.value) })}
        />

        <Input
          label="Max score"
          type="number"
          min={0}
          max={100}
          value={params.max_score ?? ''}
          onChange={(e) => onChange({ max_score: toNumber(e.target.value) })}
        />
      </div>

      {activeFilterCount > 0 && (
        <div className="mt-3 flex items-center justify-between">
          <span className="text-xs text-slate-500">
            {activeFilterCount} filter{activeFilterCount === 1 ? '' : 's'} applied
          </span>
          <button type="button" className="btn-ghost text-sm" onClick={onClear}>
            <X className="h-4 w-4" aria-hidden="true" />
            Clear all
          </button>
        </div>
      )}
    </div>
  );
}
