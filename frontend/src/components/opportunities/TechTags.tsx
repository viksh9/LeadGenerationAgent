import { Badge } from '@/components/ui/Badge';

/** Up to `max` technology tags, then "+N" with the full list on hover. */
export function TechTags({ technologies, max = 3 }: { technologies: string[]; max?: number }) {
  if (!technologies || technologies.length === 0) return <span className="text-slate-400">—</span>;
  const shown = technologies.slice(0, max);
  const extra = technologies.length - shown.length;
  return (
    <span className="flex flex-wrap items-center gap-1">
      {shown.map((t) => (
        <Badge key={t}>{t}</Badge>
      ))}
      {extra > 0 && (
        <span className="text-xs text-slate-500" title={technologies.join(', ')}>
          {`+${extra}`}
        </span>
      )}
    </span>
  );
}
