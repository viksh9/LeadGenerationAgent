import { useNavigate } from 'react-router-dom';
import { Card, CardTitle } from '@/components/ui/Card';
import { Table, Td, Th } from '@/components/ui/Table';
import { Badge, PriorityBadge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/States';
import { ScoreIndicator } from '@/components/common/ScoreIndicator';
import type { Lead } from '@/types/lead';

export function TopOpportunitiesTable({ leads }: { leads: Lead[] }) {
  const navigate = useNavigate();

  return (
    <Card padded={false}>
      <div className="flex items-center justify-between px-5 py-4">
        <CardTitle>Top Opportunities</CardTitle>
        <span className="text-xs text-slate-400 dark:text-slate-500">Sorted by score</span>
      </div>
      {leads.length === 0 ? (
        <EmptyState title="No opportunities yet" description="Analyzed leads will appear here." />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Company</Th>
              <Th>Industry</Th>
              <Th>Signal</Th>
              <Th>Score</Th>
              <Th>Priority</Th>
              <Th>Potential Opportunity</Th>
              <Th>Action</Th>
            </tr>
          </thead>
          <tbody>
            {leads.map((lead) => (
              <tr
                key={lead.id}
                className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800"
                onClick={() => navigate(`/leads/${lead.id}`)}
              >
                <Td>
                  <span className="font-medium text-slate-900 dark:text-slate-100">{lead.company_name}</span>
                </Td>
                <Td>{lead.industry ?? '—'}</Td>
                <Td>{lead.signal_type ? <Badge>{lead.signal_type}</Badge> : '—'}</Td>
                <Td>
                  <ScoreIndicator score={lead.lead_score} />
                </Td>
                <Td>
                  <PriorityBadge priority={lead.lead_priority} />
                </Td>
                <Td>
                  <span className="line-clamp-1 max-w-xs text-slate-600 dark:text-slate-300">
                    {lead.opportunity_summary ?? lead.signal_title ?? '—'}
                  </span>
                </Td>
                <Td>
                  <button
                    type="button"
                    className="btn-secondary px-2.5 py-1 text-xs"
                    onClick={(e) => {
                      e.stopPropagation();
                      navigate(`/leads/${lead.id}`);
                    }}
                    aria-label={`View ${lead.company_name}`}
                  >
                    View
                  </button>
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}
