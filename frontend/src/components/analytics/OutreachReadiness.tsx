import { Card, CardTitle } from '@/components/ui/Card';
import type { OutreachReadiness as Readiness } from '@/types/analytics';

function Stat({ label, value, tone }: { label: string; value: number; tone?: 'good' | 'warn' }) {
  const color = tone === 'good' ? 'text-emerald-700' : tone === 'warn' ? 'text-amber-700' : 'text-slate-900';
  return (
    <div className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2">
      <span className="text-sm text-slate-600">{label}</span>
      <span className={`text-sm font-semibold tabular-nums ${color}`}>{value}</span>
    </div>
  );
}

/** Outreach readiness breakdown derived from lead data (§13). */
export function OutreachReadiness({ readiness }: { readiness: Readiness }) {
  return (
    <Card>
      <CardTitle>Outreach readiness</CardTitle>
      <div className="mt-3 space-y-2">
        <Stat label="Ready for outreach" value={readiness.ready} tone="good" />
        <Stat label="Needs review" value={readiness.needsReview} tone="warn" />
        <Stat label="Missing POC role" value={readiness.missingPoc} />
        <Stat label="Missing pitch" value={readiness.missingPitch} />
        <Stat label="Low confidence" value={readiness.lowConfidence} />
      </div>
    </Card>
  );
}
