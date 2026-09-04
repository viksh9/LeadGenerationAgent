import { Loader2 } from 'lucide-react';
import { STATUSES } from '@/constants/leads';
import { useUpdateLead } from '@/hooks/useLeads';
import type { LeadStatus } from '@/types/lead';

/**
 * Compact inline status editor for a table row. Persists via PUT /leads/{id}.
 * Calculated fields (score/priority) are never editable — only workflow status.
 */
export function LeadStatusSelect({
  leadId,
  status,
  company,
}: {
  leadId: number;
  status: LeadStatus;
  company: string;
}) {
  const mutation = useUpdateLead(leadId);
  return (
    <span className="inline-flex items-center gap-1">
      <select
        className="select w-auto px-2 py-1 text-xs"
        value={status}
        disabled={mutation.isPending}
        aria-label={`Status for ${company}`}
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => mutation.mutate({ status: e.target.value as LeadStatus })}
      >
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      {mutation.isPending && (
        <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" aria-hidden="true" />
      )}
    </span>
  );
}
