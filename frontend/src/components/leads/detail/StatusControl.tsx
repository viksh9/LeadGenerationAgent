import { Check, Loader2 } from 'lucide-react';
import { STATUSES } from '@/constants/leads';
import { useUpdateLead } from '@/hooks/useLeads';
import type { LeadStatus } from '@/types/lead';

/** Editable lead status — persists via PUT /leads/{id}. */
export function StatusControl({ leadId, status }: { leadId: number; status: LeadStatus }) {
  const mutation = useUpdateLead(leadId);

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="lead-status" className="text-sm text-slate-500">
        Status
      </label>
      <select
        id="lead-status"
        className="select w-auto py-1.5"
        value={status}
        disabled={mutation.isPending}
        onChange={(e) => mutation.mutate({ status: e.target.value as LeadStatus })}
      >
        {STATUSES.map((s) => (
          <option key={s} value={s}>
            {s}
          </option>
        ))}
      </select>
      {mutation.isPending && <Loader2 className="h-4 w-4 animate-spin text-slate-400" aria-hidden="true" />}
      {mutation.isSuccess && !mutation.isPending && (
        <Check className="h-4 w-4 text-emerald-500" aria-label="Saved" />
      )}
    </div>
  );
}
