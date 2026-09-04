import { useNavigate } from 'react-router-dom';
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react';
import { Table, Td, Th } from '@/components/ui/Table';
import { Badge, PriorityBadge } from '@/components/ui/Badge';
import { ScoreIndicator } from '@/components/common/ScoreIndicator';
import { formatDate } from '@/utils/format';
import type { SortBy } from '@/constants/leads';
import type { Lead, LeadListParams } from '@/types/lead';

interface LeadsTableProps {
  leads: Lead[];
  params: LeadListParams;
  onSort: (column: SortBy) => void;
}

function SortHeader({
  column,
  label,
  params,
  onSort,
}: {
  column: SortBy;
  label: string;
  params: LeadListParams;
  onSort: (c: SortBy) => void;
}) {
  const active = params.sort_by === column;
  const Icon = active ? (params.sort_order === 'asc' ? ArrowUp : ArrowDown) : ChevronsUpDown;
  return (
    <th scope="col" className="border-b border-slate-200 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
      <button
        type="button"
        onClick={() => onSort(column)}
        className="inline-flex items-center gap-1 hover:text-slate-800"
        aria-label={`Sort by ${label}`}
      >
        {label}
        <Icon className={active ? 'h-3.5 w-3.5 text-slate-700' : 'h-3.5 w-3.5 text-slate-300'} aria-hidden="true" />
      </button>
    </th>
  );
}

export function LeadsTable({ leads, params, onSort }: LeadsTableProps) {
  const navigate = useNavigate();
  return (
    <Table>
      <thead>
        <tr>
          <SortHeader column="company_name" label="Company" params={params} onSort={onSort} />
          <Th>Industry</Th>
          <Th>Signal</Th>
          <SortHeader column="lead_score" label="Score" params={params} onSort={onSort} />
          <Th>Priority</Th>
          <Th>Status</Th>
          <SortHeader column="signal_date" label="Signal date" params={params} onSort={onSort} />
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
              <span className="font-medium text-slate-900">{lead.company_name}</span>
              {lead.location && <span className="block text-xs text-slate-400">{lead.location}</span>}
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
              <span className="text-xs font-medium text-slate-600">{lead.status}</span>
            </Td>
            <Td>{formatDate(lead.signal_date)}</Td>
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
  );
}
