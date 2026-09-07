import { Table, Td, Th } from '@/components/ui/Table';
import { PriorityBadge } from '@/components/ui/Badge';
import { ScoreIndicator } from '@/components/common/ScoreIndicator';
import { OpportunityTypeBadge, StaffingNeedBadge, UrgencyBadge } from '@/components/opportunities/badges';
import { TechTags } from '@/components/opportunities/TechTags';
import type { Opportunity } from '@/types/opportunity';

interface OpportunityTableProps {
  opportunities: Opportunity[];
  onOpen: (opportunity: Opportunity) => void;
}

/** Compact opportunities table (desktop/tablet). Rows open the detail drawer. */
export function OpportunityTable({ opportunities, onOpen }: OpportunityTableProps) {
  return (
    <Table>
      <thead>
        <tr>
          <Th>Company</Th>
          <Th>Opportunity</Th>
          <Th>Staffing</Th>
          <Th>Est. team</Th>
          <Th>Technologies</Th>
          <Th>Urgency</Th>
          <Th>Score</Th>
          <Th>Priority</Th>
          <Th>Status</Th>
          <Th>Action</Th>
        </tr>
      </thead>
      <tbody>
        {opportunities.map((o) => (
          <tr
            key={o.leadId}
            className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800"
            onClick={() => onOpen(o)}
          >
            <Td>
              <span className="font-medium text-slate-900 dark:text-slate-100">{o.company}</span>
              {o.industry && <span className="block text-xs text-slate-400 dark:text-slate-500">{o.industry}</span>}
            </Td>
            <Td>
              <OpportunityTypeBadge type={o.opportunityType} />
            </Td>
            <Td>
              <StaffingNeedBadge need={o.staffingNeed} />
            </Td>
            <Td>
              <span className="whitespace-nowrap tabular-nums text-slate-700 dark:text-slate-300">
                {o.estimatedHiring != null ? `${o.estimatedHiring} eng` : 'Not available'}
              </span>
            </Td>
            <Td>
              <TechTags technologies={o.technologies} />
            </Td>
            <Td>
              <UrgencyBadge urgency={o.urgency} reason={o.urgencyReason} />
            </Td>
            <Td>
              <ScoreIndicator score={o.score} />
            </Td>
            <Td>
              <PriorityBadge priority={o.priority} />
            </Td>
            <Td>
              <span className="text-xs font-medium text-slate-600 dark:text-slate-300">{o.status}</span>
            </Td>
            <Td>
              <button
                type="button"
                className="btn-secondary px-2.5 py-1 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  onOpen(o);
                }}
                aria-label={`View opportunity for ${o.company}`}
              >
                View
              </button>
            </Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
