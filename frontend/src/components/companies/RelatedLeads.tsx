import { Card } from '@/components/ui/Card';
import { CompanySignalsTable } from '@/components/companies/CompanySignalsTable';
import type { CompanyIntelligence } from '@/types/company';

/** The account's highest-value leads (top 8). Reuses the signals table. */
export function RelatedLeads({ company }: { company: CompanyIntelligence }) {
  const leads = company.leads.slice(0, 8);
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-slate-900">Related leads ({company.leadCount})</h3>
      <Card padded={false}>
        <CompanySignalsTable leads={leads} />
      </Card>
    </div>
  );
}
