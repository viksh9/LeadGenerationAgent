import { CopyButton } from '@/components/leads/detail/primitives';
import type { OutreachItem } from '@/types/outreach';

/** Call channel. Talking points are not persisted in this phase. */
export function CallTalkingPoints({ item }: { item: OutreachItem }) {
  const points = item.message.talkingPoints;
  if (points.length === 0) {
    return <p className="text-sm text-slate-400 dark:text-slate-500">No call talking points have been generated.</p>;
  }
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">Talking points</p>
        <CopyButton text={points.map((p, i) => `${i + 1}. ${p}`).join('\n')} label="Copy talking points" />
      </div>
      <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-700 dark:text-slate-300">
        {points.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ol>
    </div>
  );
}
