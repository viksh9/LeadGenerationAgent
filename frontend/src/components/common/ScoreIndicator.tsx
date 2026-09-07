import { priorityColor, scoreBand } from '@/utils/format';

/** Compact score readout: "96 / 100" + a band bar + text label (not colour alone). */
export function ScoreIndicator({ score }: { score: number }) {
  const value = Math.max(0, Math.min(100, Math.round(score)));
  const band = scoreBand(value);
  return (
    <div className="flex items-center gap-2" aria-label={`Score ${value} of 100, ${band}`}>
      <div className="flex flex-col">
        <span className="text-sm font-semibold tabular-nums text-slate-900 dark:text-slate-100">
          {value}
          <span className="text-xs font-normal text-slate-400 dark:text-slate-500"> / 100</span>
        </span>
        <span
          className="mt-1 h-1.5 w-16 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800"
          aria-hidden="true"
        >
          <span
            className="block h-full rounded-full"
            style={{ width: `${value}%`, backgroundColor: priorityColor[band] }}
          />
        </span>
      </div>
    </div>
  );
}
