import { useNavigate } from 'react-router-dom';
import { Card, CardTitle } from '@/components/ui/Card';
import { Table, Td, Th } from '@/components/ui/Table';
import { Badge, HiringIntensityBadge, PriorityBadge, ProvenanceBadge } from '@/components/ui/Badge';
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
              <Th>Location</Th>
              <Th>IT openings</Th>
              <Th>Intensity</Th>
              <Th>Top technologies</Th>
              <Th>Score</Th>
              <Th>Priority</Th>
              <Th>Target</Th>
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
                  <span className="flex items-center gap-2">
                    <span className="font-medium text-slate-900 dark:text-slate-100">{lead.company_name}</span>
                    <ProvenanceBadge provenance={lead.data_provenance} />
                  </span>
                </Td>
                <Td>{lead.location ?? '—'}</Td>
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
                  <span className="flex flex-wrap gap-1">
                    {lead.technologies.slice(0, 3).map((t) => (
                      <Badge key={t}>{t}</Badge>
                    ))}
                    {lead.technologies.length === 0 && <span className="text-slate-400">—</span>}
                  </span>
                </Td>
                <Td>
                  <ScoreIndicator score={lead.lead_score} />
                </Td>
                <Td>
                  <PriorityBadge priority={lead.lead_priority} />
                </Td>
                <Td>
                  <span className="whitespace-nowrap text-xs text-slate-600 dark:text-slate-300">
                    {lead.primary_target_role ?? '—'}
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
