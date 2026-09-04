import { useNavigate } from 'react-router-dom';
import { Table, Td, Th } from '@/components/ui/Table';
import { Badge, PriorityBadge } from '@/components/ui/Badge';
import { ScoreIndicator } from '@/components/common/ScoreIndicator';
import type { CompanySummary } from '@/types/company';

/** Navigate to the leads list filtered to this company. */
function companyLeadsPath(name: string) {
  return `/leads?search=${encodeURIComponent(name)}`;
}

export function CompaniesTable({ companies }: { companies: CompanySummary[] }) {
  const navigate = useNavigate();
  return (
    <Table>
      <thead>
        <tr>
          <Th>Company</Th>
          <Th>Industry</Th>
          <Th>Location</Th>
          <Th>Leads</Th>
          <Th>Best score</Th>
          <Th>Priority</Th>
          <Th>Technologies</Th>
          <Th>Action</Th>
        </tr>
      </thead>
      <tbody>
        {companies.map((company) => (
          <tr
            key={company.name}
            className="cursor-pointer hover:bg-slate-50"
            onClick={() => navigate(companyLeadsPath(company.name))}
          >
            <Td>
              <span className="font-medium text-slate-900">{company.name}</span>
              {company.companySize && (
                <span className="block text-xs text-slate-400">{company.companySize}</span>
              )}
            </Td>
            <Td>{company.industry ?? '—'}</Td>
            <Td>{company.location ?? '—'}</Td>
            <Td>
              <span className="tabular-nums">{company.leadCount}</span>
            </Td>
            <Td>
              <ScoreIndicator score={company.bestScore} />
            </Td>
            <Td>
              <PriorityBadge priority={company.topPriority} />
            </Td>
            <Td>
              {company.technologies.length === 0 ? (
                '—'
              ) : (
                <div className="flex max-w-xs flex-wrap gap-1">
                  {company.technologies.slice(0, 3).map((tech) => (
                    <Badge key={tech}>{tech}</Badge>
                  ))}
                  {company.technologies.length > 3 && (
                    <span className="text-xs text-slate-400">+{company.technologies.length - 3}</span>
                  )}
                </div>
              )}
            </Td>
            <Td>
              <button
                type="button"
                className="btn-secondary px-2.5 py-1 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  navigate(companyLeadsPath(company.name));
                }}
                aria-label={`View leads for ${company.name}`}
              >
                View leads
              </button>
            </Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}
