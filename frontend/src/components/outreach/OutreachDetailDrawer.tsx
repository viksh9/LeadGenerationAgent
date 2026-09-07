import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { X } from 'lucide-react';
import { cn } from '@/utils/cn';
import { PriorityBadge } from '@/components/ui/Badge';
import { CopyButton } from '@/components/leads/detail/primitives';
import { StaffingNeedBadge, UrgencyBadge } from '@/components/opportunities/badges';
import { TechTags } from '@/components/opportunities/TechTags';
import { MessageStrategyBadge, OutreachStatusBadge, PitchConfidence } from '@/components/outreach/badges';
import { EmailMessage } from '@/components/outreach/EmailMessage';
import { LinkedInMessage } from '@/components/outreach/LinkedInMessage';
import { CallTalkingPoints } from '@/components/outreach/CallTalkingPoints';
import { EvidenceSummary } from '@/components/outreach/EvidenceSummary';
import { OPPORTUNITY_TYPE_LABELS } from '@/services/opportunities';
import type { MessageChannel, OutreachItem } from '@/types/outreach';

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-800 dark:text-slate-200">{children}</dd>
    </div>
  );
}

const TABS: { key: MessageChannel; label: string }[] = [
  { key: 'email', label: 'Email' },
  { key: 'linkedin', label: 'LinkedIn' },
  { key: 'call', label: 'Call' },
];

/** Outreach detail drawer: opportunity context + message channels. Keyed to lead. */
export function OutreachDetailDrawer({
  item,
  onClose,
}: {
  item: OutreachItem | null;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const [channel, setChannel] = useState<MessageChannel>('email');

  useEffect(() => {
    if (!item) return;
    setChannel('email');
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [item, onClose]);

  if (!item) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Outreach for ${item.company}`}
        className="h-full w-full max-w-lg overflow-y-auto bg-white dark:bg-slate-900 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-slate-100 dark:border-slate-800 p-4">
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-slate-900 dark:text-slate-100">{item.company}</h2>
            <p className="text-xs text-slate-400 dark:text-slate-500">
              {item.role ?? 'Target role not identified'}
              {item.industry ? ` · ${item.industry}` : ''}
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="rounded-md p-1 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 hover:text-slate-700 dark:hover:text-slate-300"
            onClick={onClose}
            aria-label="Close outreach details"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </div>

        <div className="space-y-4 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <PriorityBadge priority={item.priority} />
            <OutreachStatusBadge status={item.status} />
            <StaffingNeedBadge need={item.staffingNeed} />
            <UrgencyBadge urgency={item.urgency} reason={item.urgencyReason} />
          </div>

          <dl className="grid grid-cols-2 gap-3">
            <Row label="Opportunity">{OPPORTUNITY_TYPE_LABELS[item.opportunityType]}</Row>
            <Row label="Score">
              <span className="font-semibold tabular-nums">{Math.round(item.score)} / 100</span>
            </Row>
            <Row label="Message strategy">
              <MessageStrategyBadge strategy={item.messageStrategy} />
            </Row>
            <Row label="Pitch confidence">
              <PitchConfidence confidence={item.pitchConfidence} />
            </Row>
            <Row label="Estimated team">
              {item.estimatedHiring != null ? `${item.estimatedHiring} engineers` : 'Not available'}
            </Row>
            <Row label="Lead status">{item.leadStatus}</Row>
          </dl>

          {item.opportunitySummary && <Row label="Opportunity reason">{item.opportunitySummary}</Row>}

          <Row label="Technologies">
            <TechTags technologies={item.technologies} max={12} />
          </Row>

          {item.recommendedAction && (
            <div className="rounded-lg border border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40 p-3">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">
                  Recommended action
                </p>
                <CopyButton text={item.recommendedAction} label="Copy recommended action" />
              </div>
              <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">{item.recommendedAction}</p>
            </div>
          )}

          <EvidenceSummary item={item} />

          {/* Message channels */}
          <div>
            <div className="flex gap-1 border-b border-slate-200 dark:border-slate-800" role="tablist" aria-label="Message channels">
              {TABS.map((t) => (
                <button
                  key={t.key}
                  type="button"
                  role="tab"
                  aria-selected={channel === t.key}
                  onClick={() => setChannel(t.key)}
                  className={cn(
                    '-mb-px border-b-2 px-3 py-2 text-sm font-medium',
                    channel === t.key
                      ? 'border-brand-600 text-brand-700'
                      : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200',
                  )}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <div className="pt-4" role="tabpanel">
              {channel === 'email' && <EmailMessage item={item} />}
              {channel === 'linkedin' && <LinkedInMessage item={item} />}
              {channel === 'call' && <CallTalkingPoints item={item} />}
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Link to={`/leads/${item.leadId}`} className="btn-primary flex-1 justify-center">
              View lead
            </Link>
            <Link
              to={`/companies/${encodeURIComponent(item.company)}`}
              className="btn-secondary flex-1 justify-center"
            >
              View company
            </Link>
            <Link
              to={`/opportunities?search=${encodeURIComponent(item.company)}`}
              className="btn-secondary flex-1 justify-center"
            >
              View opportunity
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
