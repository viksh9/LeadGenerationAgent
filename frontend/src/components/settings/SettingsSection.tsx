import type { ReactNode } from 'react';
import { Card } from '@/components/ui/Card';

/** A titled settings card with an optional description. */
export function SettingsSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <Card>
      <div>
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        {description && <p className="mt-0.5 text-sm text-slate-500">{description}</p>}
      </div>
      <div className="mt-4">{children}</div>
    </Card>
  );
}

/** A label / control row. */
export function SettingRow({ label, hint, control }: { label: string; hint?: string; control: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 border-t border-slate-100 py-3 first:border-t-0 first:pt-0 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="text-sm font-medium text-slate-800">{label}</p>
        {hint && <p className="text-xs text-slate-400">{hint}</p>}
      </div>
      <div className="shrink-0">{control}</div>
    </div>
  );
}
