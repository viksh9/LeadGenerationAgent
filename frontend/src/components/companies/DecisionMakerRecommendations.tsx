import { DetailCard } from '@/components/leads/detail/DetailCard';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import type { CompanyIntelligence } from '@/types/company';

/**
 * Recommended decision-maker ROLES aggregated across the account's leads,
 * strongest (most-referenced) first. A person is named only when a lead
 * actually provides one — relevance scores are not stored, so lead frequency is
 * shown instead of an invented relevance number.
 */
export function DecisionMakerRecommendations({ company }: { company: CompanyIntelligence }) {
  const roles = company.decisionMakers;
  return (
    <DetailCard title="Recommended decision-makers">
      {roles.length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-slate-500">No decision-maker roles recommended yet.</p>
      ) : (
        <ul className="divide-y divide-slate-100 dark:divide-slate-800">
          {roles.map((dm) => (
            <li key={dm.role} className="flex items-center justify-between gap-3 py-2.5">
              <div className="min-w-0">
                <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{dm.role}</p>
                {dm.name && <p className="text-xs text-slate-500 dark:text-slate-400">{dm.name}</p>}
              </div>
              <div className="flex items-center gap-3 text-xs text-slate-400 dark:text-slate-500">
                <span aria-label={`${dm.leadCount} related leads`}>
                  {dm.leadCount} lead{dm.leadCount === 1 ? '' : 's'}
                </span>
                {dm.linkedinUrl && <ExternalLinkValue href={dm.linkedinUrl} label="LinkedIn" />}
              </div>
            </li>
          ))}
        </ul>
      )}
    </DetailCard>
  );
}
