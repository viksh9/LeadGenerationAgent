import type { ContactSummary } from '@/types/contact';

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div className="card card-pad">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">{value}</p>
    </div>
  );
}

/** Role-recommendation summary (wording avoids implying unique real people). */
export function ContactSummaryCards({ summary }: { summary: ContactSummary }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Kpi label="Role recommendations" value={summary.total} />
      <Kpi label="High relevance" value={summary.highRelevance} />
      <Kpi label="Technical roles" value={summary.technical} />
      <Kpi label="Procurement / vendor" value={summary.procurementVendor} />
    </div>
  );
}
