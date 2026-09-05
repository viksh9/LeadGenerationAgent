import { Search, X } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { STATUSES } from '@/constants/leads';
import {
  OPPORTUNITY_TYPES,
  OPPORTUNITY_TYPE_LABELS,
  PRIORITIES,
  STAFFING_NEEDS,
  URGENCIES,
} from '@/services/opportunities';
import type { OpportunityFilterState } from '@/types/opportunity';

type Patch = Partial<OpportunityFilterState>;

interface Props {
  filters: OpportunityFilterState;
  searchText: string;
  onSearchText: (value: string) => void;
  onChange: (patch: Patch) => void;
  onClear: () => void;
}

const CHIP_LABELS: Record<keyof OpportunityFilterState, string> = {
  search: 'Search',
  type: 'Type',
  priority: 'Priority',
  staffing: 'Staffing',
  urgency: 'Urgency',
  industry: 'Industry',
  technology: 'Tech',
  status: 'Status',
};

function chipText(key: keyof OpportunityFilterState, value: string): string {
  if (key === 'type') return `Type: ${OPPORTUNITY_TYPE_LABELS[value as keyof typeof OPPORTUNITY_TYPE_LABELS]}`;
  if (key === 'search') return `Search: "${value}"`;
  return `${CHIP_LABELS[key]}: ${value}`;
}

export function OpportunityFilters({ filters, searchText, onSearchText, onChange, onClear }: Props) {
  const s = (v: string) => (v === '' ? '' : v);
  const activeChips = (Object.keys(filters) as (keyof OpportunityFilterState)[])
    .filter((k) => k !== 'search' && filters[k] !== '')
    .map((k) => ({ key: k, label: chipText(k, filters[k]) }));

  return (
    <div className="space-y-3">
      <div className="card card-pad">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="sm:col-span-2 lg:col-span-2">
            <label className="label" htmlFor="opp-search">
              Search
            </label>
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
                aria-hidden="true"
              />
              <input
                id="opp-search"
                className="input pl-9"
                placeholder="Search opportunities..."
                value={searchText}
                onChange={(e) => onSearchText(e.target.value)}
              />
            </div>
          </div>

          <Select
            label="Opportunity type"
            value={filters.type}
            onChange={(e) => onChange({ type: s(e.target.value) as OpportunityFilterState['type'] })}
          >
            <option value="">All types</option>
            {OPPORTUNITY_TYPES.map((t) => (
              <option key={t} value={t}>
                {OPPORTUNITY_TYPE_LABELS[t]}
              </option>
            ))}
          </Select>

          <Select
            label="Priority"
            value={filters.priority}
            onChange={(e) => onChange({ priority: s(e.target.value) as OpportunityFilterState['priority'] })}
          >
            <option value="">All priorities</option>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </Select>

          <Select
            label="Staffing need"
            value={filters.staffing}
            onChange={(e) => onChange({ staffing: s(e.target.value) as OpportunityFilterState['staffing'] })}
          >
            <option value="">All staffing</option>
            {STAFFING_NEEDS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>

          <Select
            label="Urgency"
            value={filters.urgency}
            onChange={(e) => onChange({ urgency: s(e.target.value) as OpportunityFilterState['urgency'] })}
          >
            <option value="">All urgency</option>
            {URGENCIES.map((u) => (
              <option key={u} value={u}>
                {u}
              </option>
            ))}
          </Select>

          <Select
            label="Status"
            value={filters.status}
            onChange={(e) => onChange({ status: s(e.target.value) as OpportunityFilterState['status'] })}
          >
            <option value="">All statuses</option>
            {STATUSES.map((st) => (
              <option key={st} value={st}>
                {st}
              </option>
            ))}
          </Select>

          <Input
            label="Industry"
            placeholder="e.g. BFSI"
            value={filters.industry}
            onChange={(e) => onChange({ industry: e.target.value })}
          />

          <Input
            label="Technology"
            placeholder="e.g. Java"
            value={filters.technology}
            onChange={(e) => onChange({ technology: e.target.value })}
          />
        </div>
      </div>

      {activeChips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2" aria-label="Active filters">
          {activeChips.map(({ key, label }) => (
            <span key={key} className="chip">
              {label}
              <button
                type="button"
                className="rounded-full p-0.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
                onClick={() => onChange({ [key]: '' } as Patch)}
                aria-label={`Remove filter ${label}`}
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </span>
          ))}
          <button
            type="button"
            className="text-xs font-medium text-brand-600 hover:text-brand-700"
            onClick={onClear}
          >
            Clear all
          </button>
        </div>
      )}
    </div>
  );
}
