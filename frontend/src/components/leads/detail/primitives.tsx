import { useState } from 'react';
import { Check, Copy, ExternalLink } from 'lucide-react';
import { Badge } from '@/components/ui/Badge';

/** A row of badge chips, or an em dash when empty. */
export function Chips({ items }: { items: string[] }) {
  if (!items || items.length === 0) return <span className="text-slate-400">—</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <Badge key={item}>{item}</Badge>
      ))}
    </div>
  );
}

/** A safely-opened external link (or em dash). Optionally strips the scheme. */
export function ExternalLinkValue({
  href,
  label,
  stripScheme = false,
}: {
  href: string | null | undefined;
  label?: string;
  stripScheme?: boolean;
}) {
  if (!href) return <span className="text-slate-400">—</span>;
  const text = label ?? (stripScheme ? href.replace(/^https?:\/\//, '') : href);
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-brand-600 hover:underline"
    >
      <span className="truncate">{text}</span>
      <ExternalLink className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
    </a>
  );
}

/**
 * Copy-to-clipboard button with a transient "Copied" state and an accessible
 * label. No browser alerts — feedback is inline and aria-live.
 */
export function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard may be unavailable (insecure context) — fail quietly.
    }
  };

  return (
    <button type="button" className="btn-ghost text-sm" onClick={copy} aria-label={label}>
      {copied ? (
        <Check className="h-4 w-4 text-emerald-500" aria-hidden="true" />
      ) : (
        <Copy className="h-4 w-4" aria-hidden="true" />
      )}
      <span aria-live="polite">{copied ? 'Copied' : 'Copy'}</span>
    </button>
  );
}
