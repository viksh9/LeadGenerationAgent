import { useNavigate } from 'react-router-dom';
import { Table, Td, Th } from '@/components/ui/Table';
import { Badge, PriorityBadge } from '@/components/ui/Badge';
import { ScoreIndicator } from '@/components/common/ScoreIndicator';
import { humanizeSignal } from '@/constants/leads';
import { formatDate } from '@/utils/format';
import type { Lead } from '@/types/lead';

/** The company's leads, each presented as a signal/opportunity row. */
export function CompanySignalsTable({ leads }: { leads: Lead[] }) {
  const navigate = useNavigate();
  return (
    <Table>
      <thead>
        <tr>
          <Th>Signal</Th>
          <Th>Opportunity</Th>
          <Th>Score</Th>
          <Th>Priority</Th>
          <Th>Status</Th>
          <Th>Signal date</Th>
          <Th>Action</Th>
        </tr>
      </thead>
      <tbody>
        {leads.map((lead) => (
          <tr
            key={lead.id}
            className="cursor-pointer hover:bg-slate-50"
            onClick={() => navigate(`/leads/${lead.id}`)}
          >
            <Td>
              {lead.signal_type ? (
                <div>
                  <Badge className="whitespace-nowrap">{humanizeSignal(lead.signal_type)}</Badge>
                  {lead.signal_title && (
                    <span className="mt-1 block max-w-[16rem] truncate text-xs text-slate-500" title={lead.signal_title}>
                      {lead.signal_title}
                    </span>
                  )}
                </div>
              ) : (
                <span className="text-slate-400">—</span>
              )}
            </Td>
            <Td>
              {lead.opportunity_summary ? (
                <span className="block max-w-[18rem] truncate text-slate-700" title={lead.opportunity_summary}>
                  {lead.opportunity_summary}
                </span>
              ) : (
                <span className="text-slate-400">—</span>
              )}
            </Td>
            <Td>
              <ScoreIndicator score={lead.lead_score} />
            </Td>
            <Td>
              <PriorityBadge priority={lead.lead_priority} />
            </Td>
            <Td>
              <span className="text-xs font-medium text-slate-600">{lead.status}</span>
            </Td>
            <Td>
              <span className="whitespace-nowrap">{formatDate(lead.signal_date)}</span>
            </Td>
            <Td>
              <button
                type="button"
                className="btn-secondary px-2.5 py-1 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(`/leads/${lead.id}`);
                }}
                aria-label={`View lead ${lead.id}`}
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
