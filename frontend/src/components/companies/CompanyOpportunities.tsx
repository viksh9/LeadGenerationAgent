import { useNavigate } from 'react-router-dom';
import { PriorityBadge } from '@/components/ui/Badge';
import { DetailCard } from '@/components/leads/detail/DetailCard';
import type { CompanyIntelligence } from '@/types/company';

/**
 * Opportunities from the account's leads. Structured staffing band / team size /
 * urgency are produced at analysis time and not persisted, so each opportunity
 * shows what is stored: summary, estimated staffing, score, priority, status.
 */
export function CompanyOpportunities({ company }: { company: CompanyIntelligence }) {
  const navigate = useNavigate();
  const opportunities = company.opportunities;

  return (
    <DetailCard title="Potential opportunities">
      {opportunities.length === 0 ? (
        <p className="text-sm text-slate-400">No opportunities identified from current signals.</p>
      ) : (
        <ul className="space-y-3">
          {opportunities.map((opp) => (
            <li key={opp.leadId} className="rounded-lg border border-slate-100 p-3">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm text-slate-800">{opp.summary ?? 'Opportunity'}</p>
                <PriorityBadge priority={opp.priority} />
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-slate-400">
                <span>
                  Est. staffing:{' '}
                  <span className="font-medium text-slate-600">
                    {opp.estimatedHiring ? `${opp.estimatedHiring} engineers` : 'Not available'}
                  </span>
                </span>
                <span>
                  Score: <span className="font-medium tabular-nums text-slate-600">{Math.round(opp.score)}</span>
                </span>
                <span>Status: <span className="font-medium text-slate-600">{opp.status}</span></span>
                <button
                  type="button"
                  className="ml-auto text-brand-600 hover:underline"
                  onClick={() => navigate(`/leads/${opp.leadId}`)}
                  aria-label={`View lead ${opp.leadId}`}
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
