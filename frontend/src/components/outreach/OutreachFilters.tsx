import { Search, X } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { OUTREACH_STATUSES, OUTREACH_STATUS_LABELS, PRIORITIES } from '@/services/outreach';
import { OPPORTUNITY_TYPES, OPPORTUNITY_TYPE_LABELS } from '@/services/opportunities';
import type { OutreachFilterState } from '@/types/outreach';

type Patch = Partial<OutreachFilterState>;

interface Props {
  filters: OutreachFilterState;
  searchText: string;
  onSearchText: (value: string) => void;
  onChange: (patch: Patch) => void;
  onClear: () => void;
}

function chipText(key: keyof OutreachFilterState, value: string): string {
  switch (key) {
    case 'priority':
      return `Priority: ${value}`;
    case 'opportunityType':
      return `Opportunity: ${OPPORTUNITY_TYPE_LABELS[value as keyof typeof OPPORTUNITY_TYPE_LABELS]}`;
    case 'status':
      return `Status: ${OUTREACH_STATUS_LABELS[value as keyof typeof OUTREACH_STATUS_LABELS]}`;
    case 'industry':
      return `Industry: ${value}`;
    case 'role':
      return `Role: ${value}`;
    case 'minScore':
      return `Score: ${value}+`;
    default:
      return `${key}: ${value}`;
  }
}

export function OutreachFilters({ filters, searchText, onSearchText, onChange, onClear }: Props) {
  const chips = (Object.keys(filters) as (keyof OutreachFilterState)[])
    .filter((k) => k !== 'search' && filters[k] !== '')
    .map((k) => ({ key: k, label: chipText(k, filters[k]) }));

  return (
    <div className="space-y-3">
      <div className="card card-pad">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="sm:col-span-2 lg:col-span-2">
            <label className="label" htmlFor="outreach-search">
              Search
            </label>
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500"
                aria-hidden="true"
              />
              <input
                id="outreach-search"
                className="input pl-9"
                placeholder="Search company, opportunity, or target role..."
                value={searchText}
                onChange={(e) => onSearchText(e.target.value)}
              />
            </div>
          </div>

          <Select
            label="Priority"
            value={filters.priority}
            onChange={(e) => onChange({ priority: e.target.value as OutreachFilterState['priority'] })}
          >
            <option value="">All priorities</option>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </Select>

          <Select
            label="Opportunity type"
            value={filters.opportunityType}
            onChange={(e) => onChange({ opportunityType: e.target.value as OutreachFilterState['opportunityType'] })}
          >
            <option value="">All opportunities</option>
            {OPPORTUNITY_TYPES.map((t) => (
              <option key={t} value={t}>
                {OPPORTUNITY_TYPE_LABELS[t]}
              </option>
            ))}
          </Select>

          <Select
            label="Message status"
            value={filters.status}
            onChange={(e) => onChange({ status: e.target.value as OutreachFilterState['status'] })}
          >
            <option value="">All statuses</option>
            {OUTREACH_STATUSES.map((s) => (
              <option key={s} value={s}>
                {OUTREACH_STATUS_LABELS[s]}
              </option>
            ))}
          </Select>

          <Input
            label="Target role"
            placeholder="e.g. VP Engineering"
            value={filters.role}
            onChange={(e) => onChange({ role: e.target.value })}
          />

          <Input
            label="Industry"
            placeholder="e.g. BFSI"
            value={filters.industry}
            onChange={(e) => onChange({ industry: e.target.value })}
          />

          <Input
            label="Min score"
            type="number"
            min={0}
            max={100}
            value={filters.minScore}
            onChange={(e) => onChange({ minScore: e.target.value })}
          />
        </div>
      </div>

      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2" aria-label="Active filters">
          {chips.map(({ key, label }) => (
            <span key={key} className="chip">
              {label}
              <button
                type="button"
                className="rounded-full p-0.5 text-slate-400 dark:text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-700 hover:text-slate-700 dark:hover:text-slate-300"
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
