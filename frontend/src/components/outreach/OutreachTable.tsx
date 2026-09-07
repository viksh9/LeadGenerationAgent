import { Table, Td, Th } from '@/components/ui/Table';
import { PriorityBadge } from '@/components/ui/Badge';
import { ScoreIndicator } from '@/components/common/ScoreIndicator';
import { OutreachStatusBadge } from '@/components/outreach/badges';
import { OPPORTUNITY_TYPE_LABELS } from '@/services/opportunities';
import { formatDate } from '@/utils/format';
import type { OutreachItem } from '@/types/outreach';

interface Props {
  items: OutreachItem[];
  onOpen: (item: OutreachItem) => void;
}

/** Outreach queue table. Rows open the message/detail drawer. */
export function OutreachTable({ items, onOpen }: Props) {
  return (
    <Table>
      <thead>
        <tr>
          <Th>Company</Th>
          <Th>Target role</Th>
          <Th>Opportunity</Th>
          <Th>Score</Th>
          <Th>Priority</Th>
          <Th>Message status</Th>
          <Th>Last activity</Th>
          <Th>Action</Th>
        </tr>
      </thead>
      <tbody>
        {items.map((o) => (
          <tr key={o.leadId} className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800" onClick={() => onOpen(o)}>
            <Td>
              <span className="font-medium text-slate-900 dark:text-slate-100">{o.company}</span>
              {o.industry && <span className="block text-xs text-slate-400 dark:text-slate-500">{o.industry}</span>}
            </Td>
            <Td>{o.role ?? '—'}</Td>
            <Td>
              <span className="whitespace-nowrap text-slate-700 dark:text-slate-300">
                {OPPORTUNITY_TYPE_LABELS[o.opportunityType]}
              </span>
            </Td>
            <Td>
              <ScoreIndicator score={o.score} />
            </Td>
            <Td>
              <PriorityBadge priority={o.priority} />
            </Td>
            <Td>
              <OutreachStatusBadge status={o.status} />
            </Td>
            <Td>
              <span className="whitespace-nowrap text-xs text-slate-500 dark:text-slate-400">{formatDate(o.updatedAt)}</span>
            </Td>
            <Td>
              <button
                type="button"
                className="btn-secondary px-2.5 py-1 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  onOpen(o);
                }}
                aria-label={`Review outreach for ${o.company}`}
              >
                Review
              </button>
            </Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
