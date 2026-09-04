import { useState } from 'react';
import { Check, Copy } from 'lucide-react';

/** Recommended pitch text with a copy-to-clipboard control. */
export function PitchBlock({ pitch }: { pitch: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(pitch);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard may be unavailable (e.g. insecure context) — fail quietly.
    }
  };

  return (
    <div>
      <div className="mb-2 flex justify-end">
        <button type="button" className="btn-ghost text-sm" onClick={copy} aria-label="Copy pitch">
          {copied ? (
            <Check className="h-4 w-4 text-emerald-500" aria-hidden="true" />
          ) : (
            <Copy className="h-4 w-4" aria-hidden="true" />
          )}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 p-4 font-sans text-sm leading-relaxed text-slate-700">
        {pitch}
      </pre>
    </div>
  );
}
