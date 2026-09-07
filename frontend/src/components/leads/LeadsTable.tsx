import { useLocation, useNavigate } from 'react-router-dom';
import { ArrowDown, ArrowUp, ChevronsUpDown, Trash2 } from 'lucide-react';
import { Table, Td } from '@/components/ui/Table';
import { Badge, HiringIntensityBadge, PriorityBadge, ProvenanceBadge } from '@/components/ui/Badge';
import { ScoreIndicator } from '@/components/common/ScoreIndicator';
import { LeadStatusSelect } from '@/components/leads/LeadStatusSelect';
import { humanizeSignal } from '@/constants/leads';
import { formatDate } from '@/utils/format';
import type { SortBy } from '@/constants/leads';
import type { Lead, LeadListParams } from '@/types/lead';

interface LeadsTableProps {
  leads: Lead[];
  params: LeadListParams;
  onSort: (column: SortBy) => void;
  onDelete: (lead: Lead) => void;
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
    <th
      scope="col"
      className="border-b border-slate-200 dark:border-slate-800 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400"
    >
      <button
        type="button"
        onClick={() => onSort(column)}
        className="inline-flex items-center gap-1 hover:text-slate-800 dark:hover:text-slate-200"
        aria-label={`Sort by ${label}`}
      >
        {label}
        <Icon
          className={active ? 'h-3.5 w-3.5 text-slate-700 dark:text-slate-300' : 'h-3.5 w-3.5 text-slate-300 dark:text-slate-600'}
          aria-hidden="true"
        />
      </button>
    </th>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th
      scope="col"
      className="whitespace-nowrap border-b border-slate-200 dark:border-slate-800 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400"
    >
      {children}
    </th>
  );
}

/** Up to two technology chips, then "+N more" (full list on hover). */
function TechList({ technologies }: { technologies: string[] }) {
  if (!technologies || technologies.length === 0) return <span className="text-slate-400 dark:text-slate-500">—</span>;
  const shown = technologies.slice(0, 2);
  const extra = technologies.length - shown.length;
  return (
    <span className="flex flex-wrap items-center gap-1">
      {shown.map((t) => (
        <Badge key={t}>{t}</Badge>
      ))}
      {extra > 0 && (
        <span className="text-xs text-slate-500 dark:text-slate-400" title={technologies.join(', ')}>
          {`+${extra} more`}
        </span>
      )}
    </span>
  );
}

export function LeadsTable({ leads, params, onSort, onDelete }: LeadsTableProps) {
  const navigate = useNavigate();
  const location = useLocation();
  // Carry the active filters so Lead Details can restore them on "Back to leads".
  const openLead = (id: number) =>
    navigate(`/leads/${id}`, { state: { leadsSearch: location.search } });
  return (
    <Table>
      <thead>
        <tr>
          <SortHeader column="company_name" label="Company" params={params} onSort={onSort} />
          <Th>IT openings</Th>
          <Th>Intensity</Th>
          <Th>Signal</Th>
          <Th>Top technologies</Th>
          <Th>Target</Th>
          <Th>Sources</Th>
          <SortHeader column="lead_score" label="Score" params={params} onSort={onSort} />
          <Th>Priority</Th>
          <Th>Status</Th>
          <Th>Action</Th>
        </tr>
      </thead>
      <tbody>
        {leads.map((lead) => (
          <tr
            key={lead.id}
            className="cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800"
            onClick={() => openLead(lead.id)}
          >
            <Td>
              <span className="flex items-center gap-2">
                <span className="font-medium text-slate-900 dark:text-slate-100">{lead.company_name}</span>
                <ProvenanceBadge provenance={lead.data_provenance} />
              </span>
              {lead.location && <span className="block text-xs text-slate-400 dark:text-slate-500">{lead.location}</span>}
            </Td>
            <Td>
              <span className="font-medium text-slate-900 dark:text-slate-100">{lead.it_job_count}</span>
              {lead.recent_job_count > 0 && (
                <span className="block text-xs text-emerald-600 dark:text-emerald-400">
                  {lead.recent_job_count} recent
                </span>
              )}
            </Td>
            <Td>
              <HiringIntensityBadge intensity={lead.hiring_intensity} />
            </Td>
            <Td>
              {lead.signal_type ? (
                <Badge className="whitespace-nowrap">
                  <span title={lead.opportunity_summary ?? lead.signal_title ?? undefined}>
                    {humanizeSignal(lead.signal_type)}
                  </span>
                </Badge>
              ) : (
                '—'
              )}
            </Td>
            <Td>
              <TechList technologies={lead.technologies} />
            </Td>
            <Td>
              <span className="whitespace-nowrap text-xs text-slate-600 dark:text-slate-300">
                {lead.primary_target_role ?? '—'}
              </span>
            </Td>
            <Td>
              <span
                className="text-slate-700 dark:text-slate-300"
                title={lead.last_signal_date ? `Last signal: ${formatDate(lead.last_signal_date)}` : undefined}
              >
                {lead.source_count}
              </span>
            </Td>
            <Td>
              <ScoreIndicator score={lead.lead_score} />
            </Td>
            <Td>
              <PriorityBadge priority={lead.lead_priority} />
            </Td>
            <Td>
              <LeadStatusSelect leadId={lead.id} status={lead.status} company={lead.company_name} />
            </Td>
            <Td>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  className="btn-secondary px-2.5 py-1 text-xs"
                  onClick={(e) => {
                    e.stopPropagation();
                    openLead(lead.id);
                  }}
                  aria-label={`View ${lead.company_name}`}
                >
                  View
                </button>
                <button
                  type="button"
                  className="rounded-md p-1.5 text-slate-400 dark:text-slate-500 hover:bg-rose-50 hover:text-rose-600"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(lead);
                  }}
                  aria-label={`Delete ${lead.company_name}`}
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            </Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
