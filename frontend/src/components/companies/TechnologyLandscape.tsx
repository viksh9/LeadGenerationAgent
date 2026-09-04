import { DetailCard } from '@/components/leads/detail/DetailCard';
import type { CompanyIntelligence } from '@/types/company';

/** Technologies across the company's leads, sorted by frequency. */
export function TechnologyLandscape({ company }: { company: CompanyIntelligence }) {
  const items = company.technologyLandscape;
  return (
    <DetailCard title="Technology landscape">
      {items.length === 0 ? (
        <p className="text-sm text-slate-400">No technologies detected across this account.</p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {items.map((tech) => (
            <li
              key={tech.name}
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700"
            >
              {tech.name}
              <span
                className="rounded-full bg-white px-1.5 tabular-nums text-slate-500"
                aria-label={`${tech.leadCount} related leads`}
              >
                {tech.leadCount}
              </span>
            </li>
          ))}
        </ul>
      )}
    </DetailCard>
  );
}
