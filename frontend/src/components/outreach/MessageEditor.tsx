import { useEffect, useState } from 'react';
import { RotateCcw } from 'lucide-react';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { CopyButton } from '@/components/leads/detail/primitives';

/**
 * Locally editable message. Edits are NOT persisted (no backend endpoint) — they
 * live in component state so the user can tweak before copying, and can reset to
 * the generated text. A confirmation guards resetting away edited content.
 */
export function MessageEditor({
  label,
  original,
  copyLabel,
  rows = 8,
}: {
  label: string;
  original: string;
  copyLabel: string;
  rows?: number;
}) {
  const [value, setValue] = useState(original);
  const [confirming, setConfirming] = useState(false);

  // Reset local edits when the source message changes (e.g. a new item opens).
  useEffect(() => setValue(original), [original]);

  const edited = value !== original;

  const requestReset = () => {
    if (edited) setConfirming(true);
    else setValue(original);
  };

  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</p>
          {edited && (
            <span className="text-xs font-medium text-amber-600" role="status">
              Unsaved changes
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="btn-ghost text-sm disabled:opacity-40"
            onClick={requestReset}
            disabled={!edited}
            aria-label="Reset to generated message"
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            Reset
          </button>
          <CopyButton text={value} label={copyLabel} />
        </div>
      </div>
      <textarea
        className="input min-h-[8rem] w-full resize-y font-sans text-sm leading-relaxed"
        rows={rows}
        value={value}
        aria-label={label}
        onChange={(e) => setValue(e.target.value)}
      />

      <ConfirmDialog
        open={confirming}
        title="Reset to generated message?"
        description="Your edits will be discarded and the original generated message restored."
        confirmLabel="Reset"
        onConfirm={() => {
          setValue(original);
          setConfirming(false);
        }}
        onCancel={() => setConfirming(false)}
      />
    </div>
  );
}
