import { Table, Td, Th } from '@/components/ui/Table';
import { PriorityBadge } from '@/components/ui/Badge';
import { DecisionMakerTypeBadge } from '@/components/contacts/badges';
import { RelevanceScore } from '@/components/contacts/RelevanceScore';
import { opportunityLabel } from '@/services/contacts';
import type { ContactRecommendation } from '@/types/contact';

interface Props {
  contacts: ContactRecommendation[];
  onOpen: (contact: ContactRecommendation) => void;
}

/** Decision-maker role recommendations table. Rows open the detail drawer. */
export function ContactTable({ contacts, onOpen }: Props) {
  return (
    <Table>
      <thead>
        <tr>
          <Th>Company</Th>
          <Th>Recommended role</Th>
          <Th>Type</Th>
          <Th>Relevance</Th>
          <Th>Opportunity</Th>
          <Th>Priority</Th>
          <Th>Source</Th>
          <Th>Confidence</Th>
          <Th>Action</Th>
        </tr>
      </thead>
      <tbody>
        {contacts.map((c) => (
          <tr key={c.id} className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800" onClick={() => onOpen(c)}>
            <Td>
              <span className="font-medium text-slate-900 dark:text-slate-100">{c.company}</span>
              {c.industry && <span className="block text-xs text-slate-400 dark:text-slate-500">{c.industry}</span>}
            </Td>
            <Td>
              <span className="font-medium text-slate-800 dark:text-slate-200">{c.role}</span>
              <span className="block text-xs text-slate-400 dark:text-slate-500">Person not identified yet</span>
            </Td>
            <Td>
              <DecisionMakerTypeBadge type={c.decisionMakerType} />
            </Td>
            <Td>
              <RelevanceScore relevance={c.relevance} />
            </Td>
            <Td>
              <span className="whitespace-nowrap text-slate-700 dark:text-slate-300">{opportunityLabel(c)}</span>
            </Td>
            <Td>
              <PriorityBadge priority={c.priority} />
            </Td>
            <Td>
              <span className="text-xs text-slate-500 dark:text-slate-400">Lead intelligence</span>
            </Td>
            <Td>
              <span className="text-xs font-medium text-slate-600 dark:text-slate-300">{c.confidence}</span>
            </Td>
            <Td>
              <button
                type="button"
                className="btn-secondary px-2.5 py-1 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  onOpen(c);
                }}
                aria-label={`View ${c.role} recommendation for ${c.company}`}
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
