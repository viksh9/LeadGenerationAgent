import { useNavigate } from 'react-router-dom';
import { Table, Td, Th } from '@/components/ui/Table';
import { PriorityBadge } from '@/components/ui/Badge';
import { ScoreIndicator } from '@/components/common/ScoreIndicator';
import { humanizeSignal } from '@/constants/leads';
import { formatDate } from '@/utils/format';
import type { CompanySummary } from '@/types/company';

/** Navigate to the leads list filtered to this company. */
function companyLeadsPath(name: string) {
  return `/leads?search=${encodeURIComponent(name)}`;
}

/** Navigate to this company's profile page. */
function companyDetailPath(name: string) {
  return `/companies/${encodeURIComponent(name)}`;
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
          <Th>Signals</Th>
          <Th>Open leads</Th>
          <Th>Best score</Th>
          <Th>Latest signal</Th>
          <Th>Priority</Th>
          <Th>Action</Th>
        </tr>
      </thead>
      <tbody>
        {companies.map((company) => (
          <tr
            key={company.name}
            className="cursor-pointer hover:bg-slate-50"
            onClick={() => navigate(companyDetailPath(company.name))}
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
              <span className="tabular-nums">{company.totalSignals}</span>
            </Td>
            <Td>
              <span className="tabular-nums">{company.leadCount}</span>
            </Td>
            <Td>
              <ScoreIndicator score={company.bestScore} />
            </Td>
            <Td>
              {company.latestSignalType ? (
                <div>
                  <span className="whitespace-nowrap text-slate-700">
                    {humanizeSignal(company.latestSignalType)}
                  </span>
                  <span className="block text-xs text-slate-400">{formatDate(company.latestSignal)}</span>
                </div>
              ) : (
                '—'
              )}
            </Td>
            <Td>
              <PriorityBadge priority={company.topPriority} />
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
