import { cn } from '@/utils/cn';
import type { Opportunity, OpportunityFilterState } from '@/types/opportunity';

type Patch = Partial<OpportunityFilterState>;

interface TabDef {
  key: string;
  label: string;
  predicate: (o: Opportunity) => boolean;
  patch: Patch;
  isActive: (f: OpportunityFilterState) => boolean;
}

const CLEARED: Patch = { type: '', priority: '', staffing: '', urgency: '' };

const TABS: TabDef[] = [
  {
    key: 'all',
    label: 'All',
    predicate: () => true,
    patch: { ...CLEARED },
    isActive: (f) => !f.type && !f.priority && !f.staffing && !f.urgency,
  },
  {
    key: 'hot',
    label: '🔥 Hot',
    predicate: (o) => o.priority === 'HOT',
    patch: { ...CLEARED, priority: 'HOT' },
    isActive: (f) => f.priority === 'HOT' && !f.type && !f.staffing && !f.urgency,
  },
  {
    key: 'high-staffing',
    label: 'High staffing need',
    predicate: (o) => o.staffingNeed === 'HIGH',
    patch: { ...CLEARED, staffing: 'HIGH' },
    isActive: (f) => f.staffing === 'HIGH' && !f.type && !f.priority && !f.urgency,
  },
  {
    key: 'high-urgency',
    label: 'High urgency',
    predicate: (o) => o.urgency === 'HIGH',
    patch: { ...CLEARED, urgency: 'HIGH' },
    isActive: (f) => f.urgency === 'HIGH' && !f.type && !f.priority && !f.staffing,
  },
  {
    key: 'project-driven',
    label: 'Project driven',
    predicate: (o) => o.opportunityType === 'PROJECT_DRIVEN_HIRING',
    patch: { ...CLEARED, type: 'PROJECT_DRIVEN_HIRING' },
    isActive: (f) => f.type === 'PROJECT_DRIVEN_HIRING' && !f.priority && !f.staffing && !f.urgency,
  },
  {
    key: 'staff-aug',
    label: 'Staff augmentation',
    predicate: (o) => o.opportunityType === 'STAFF_AUGMENTATION',
    patch: { ...CLEARED, type: 'STAFF_AUGMENTATION' },
    isActive: (f) => f.type === 'STAFF_AUGMENTATION' && !f.priority && !f.staffing && !f.urgency,
  },
  {
    key: 'vendor',
    label: 'Vendor opportunities',
    predicate: (o) => o.opportunityType === 'VENDOR_OPPORTUNITY',
    patch: { ...CLEARED, type: 'VENDOR_OPPORTUNITY' },
    isActive: (f) => f.type === 'VENDOR_OPPORTUNITY' && !f.priority && !f.staffing && !f.urgency,
  },
];

/** Convenience preset tabs. Counts are derived from the full opportunity set. */
export function QuickFilterTabs({
  opportunities,
  filters,
  onApply,
}: {
  opportunities: Opportunity[];
  filters: OpportunityFilterState;
  onApply: (patch: Patch) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2" role="tablist" aria-label="Quick opportunity filters">
      {TABS.map((tab) => {
        const count = opportunities.filter(tab.predicate).length;
        const active = tab.isActive(filters);
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onApply(tab.patch)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors',
              active
                ? 'border-brand-300 bg-brand-50 text-brand-700'
                : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800',
            )}
          >
            {tab.label}
            <span className="rounded-full bg-slate-100 dark:bg-slate-800 px-1.5 text-xs tabular-nums text-slate-500 dark:text-slate-400">
              {count}
            </span>
          </button>
        );
      })}
    </div>
  );
}
