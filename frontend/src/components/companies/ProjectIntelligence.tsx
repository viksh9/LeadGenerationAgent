import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/ui/Badge';
import { DetailCard } from '@/components/leads/detail/DetailCard';
import { humanizeSignal } from '@/constants/leads';
import { formatCurrency, formatDate } from '@/utils/format';
import type { CompanyIntelligence } from '@/types/company';

/** Projects referenced by the account's leads. Project value only shown when present. */
export function ProjectIntelligence({ company }: { company: CompanyIntelligence }) {
  const navigate = useNavigate();
  const projects = company.projects;

  return (
    <DetailCard title="Project intelligence">
      {projects.length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-slate-500">No projects referenced in this account's signals.</p>
      ) : (
        <ul className="space-y-3">
          {projects.map((project) => (
            <li key={`${project.leadId}-${project.name}`} className="rounded-lg border border-slate-100 dark:border-slate-800 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-medium text-slate-900 dark:text-slate-100">{project.name}</p>
                {project.signalType && <Badge>{humanizeSignal(project.signalType)}</Badge>}
              </div>
              {project.opportunitySummary && (
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{project.opportunitySummary}</p>
              )}
              <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-slate-400 dark:text-slate-500">
                <span>Date: {formatDate(project.date)}</span>
                {project.value != null && (
                  <span>Value: <span className="font-medium text-slate-600 dark:text-slate-300">{formatCurrency(project.value)}</span></span>
                )}
                <button
                  type="button"
                  className="ml-auto text-brand-600 hover:underline"
                  onClick={() => navigate(`/leads/${project.leadId}`)}
                >
                  View lead
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </DetailCard>
  );
}
