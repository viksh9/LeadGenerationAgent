import { X } from 'lucide-react';
import { Select } from '@/components/ui/Select';
import { INDUSTRIES, PRIORITIES, SIGNAL_LABELS, SIGNAL_TYPES } from '@/constants/leads';
import { OPPORTUNITY_TYPES, OPPORTUNITY_TYPE_LABELS } from '@/services/opportunities';
import type { AnalyticsFilters as Filters, DateRange } from '@/types/analytics';

type Patch = Partial<Filters>;

interface Props {
  filters: Filters;
  onChange: (patch: Patch) => void;
  onClear: () => void;
}

const RANGE_LABELS: Record<DateRange, string> = {
  all: 'All time',
  '7d': 'Last 7 days',
  '30d': 'Last 30 days',
  '90d': 'Last 90 days',
};

function chipText(key: keyof Filters, value: string): string {
  switch (key) {
    case 'range':
      return `Range: ${RANGE_LABELS[value as DateRange]}`;
    case 'industry':
      return `Industry: ${value}`;
    case 'priority':
      return `Priority: ${value}`;
    case 'signalType':
      return `Signal: ${SIGNAL_LABELS[value as keyof typeof SIGNAL_LABELS]}`;
    case 'opportunityType':
      return `Opportunity: ${OPPORTUNITY_TYPE_LABELS[value as keyof typeof OPPORTUNITY_TYPE_LABELS]}`;
    default:
      return `${key}: ${value}`;
  }
}

export function AnalyticsFilters({ filters, onChange, onClear }: Props) {
  const chips = (Object.keys(filters) as (keyof Filters)[])
    .filter((k) => (k === 'range' ? filters.range !== 'all' : filters[k] !== ''))
    .map((k) => ({ key: k, label: chipText(k, filters[k]) }));

  return (
    <div className="space-y-3">
      <div className="card card-pad">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <Select
            label="Date range"
            value={filters.range}
            onChange={(e) => onChange({ range: e.target.value as DateRange })}
          >
            {(Object.keys(RANGE_LABELS) as DateRange[]).map((r) => (
              <option key={r} value={r}>
                {RANGE_LABELS[r]}
              </option>
            ))}
          </Select>

          <Select
            label="Industry"
            value={filters.industry}
            onChange={(e) => onChange({ industry: e.target.value })}
          >
            <option value="">All industries</option>
            {INDUSTRIES.map((i) => (
              <option key={i} value={i}>
                {i}
              </option>
            ))}
          </Select>

          <Select
            label="Priority"
            value={filters.priority}
            onChange={(e) => onChange({ priority: e.target.value as Filters['priority'] })}
          >
            <option value="">All priorities</option>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </Select>

          <Select
            label="Signal type"
            value={filters.signalType}
            onChange={(e) => onChange({ signalType: e.target.value as Filters['signalType'] })}
          >
            <option value="">All signals</option>
            {SIGNAL_TYPES.map((s) => (
              <option key={s} value={s}>
                {SIGNAL_LABELS[s]}
              </option>
            ))}
          </Select>

          <Select
            label="Opportunity type"
            value={filters.opportunityType}
            onChange={(e) => onChange({ opportunityType: e.target.value as Filters['opportunityType'] })}
          >
            <option value="">All opportunities</option>
            {OPPORTUNITY_TYPES.map((t) => (
              <option key={t} value={t}>
                {OPPORTUNITY_TYPE_LABELS[t]}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {chips.length > 0 && (
        <div className="flex flex-wrap items-center gap-2" aria-label="Active filters">
          {chips.map(({ key, label }) => (
            <span key={key} className="chip">
              {label}
              <button
                type="button"
                className="rounded-full p-0.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
                onClick={() => onChange({ [key]: key === 'range' ? 'all' : '' } as Patch)}
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
