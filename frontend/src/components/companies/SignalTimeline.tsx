import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/ui/Badge';
import { DetailCard } from '@/components/leads/detail/DetailCard';
import { SignalStrength } from '@/components/leads/detail/SignalStrength';
import { humanizeSignal } from '@/constants/leads';
import { formatDate } from '@/utils/format';
import type { CompanyIntelligence } from '@/types/company';

/** Business-signal timeline, newest first. Each item links to its lead. */
export function SignalTimeline({ company }: { company: CompanyIntelligence }) {
  const navigate = useNavigate();
  const signals = company.signals;

  return (
    <DetailCard title="Signal timeline">
      {signals.length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-slate-500">No business signals recorded yet.</p>
      ) : (
        <ol className="relative space-y-4 border-l border-slate-200 dark:border-slate-800 pl-5">
          {signals.map((signal) => (
            <li key={signal.leadId} className="relative">
              <span
                className="absolute -left-[1.42rem] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-brand-500"
                aria-hidden="true"
              />
              <button
                type="button"
                className="w-full rounded-lg p-2 text-left hover:bg-slate-50 dark:hover:bg-slate-800"
                onClick={() => navigate(`/leads/${signal.leadId}`)}
                aria-label={`View lead ${signal.leadId} for signal ${humanizeSignal(signal.signalType)}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    {signal.signalType && <Badge>{humanizeSignal(signal.signalType)}</Badge>}
                    <span className="text-xs text-slate-400 dark:text-slate-500">{formatDate(signal.date)}</span>
                  </div>
                  <SignalStrength confidence={signal.confidence} />
                </div>
                {signal.title && (
                  <p className="mt-1 text-sm font-medium text-slate-800 dark:text-slate-200">{signal.title}</p>
                )}
                {signal.description && (
                  <p className="mt-0.5 line-clamp-2 text-sm text-slate-500 dark:text-slate-400">{signal.description}</p>
                )}
                <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
                  Related lead score: <span className="font-medium tabular-nums text-slate-600 dark:text-slate-300">{Math.round(signal.score)}</span>
                </p>
              </button>
            </li>
          ))}
        </ol>
      )}
    </DetailCard>
  );
}
