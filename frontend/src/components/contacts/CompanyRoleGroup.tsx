import { Link } from 'react-router-dom';
import { Card } from '@/components/ui/Card';
import { DecisionMakerTypeBadge } from '@/components/contacts/badges';
import type { CompanyContactGroup, ContactRecommendation } from '@/types/contact';

function RoleRow({
  contact,
  onOpen,
}: {
  contact: ContactRecommendation;
  onOpen: (c: ContactRecommendation) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(contact)}
      className="flex w-full items-center justify-between gap-3 rounded-md px-2 py-1.5 text-left hover:bg-slate-50"
      aria-label={`View ${contact.role} recommendation for ${contact.company}`}
    >
      <span className="flex min-w-0 items-center gap-2">
        <span className="truncate text-sm font-medium text-slate-800">{contact.role}</span>
        <DecisionMakerTypeBadge type={contact.decisionMakerType} />
      </span>
      <span className="shrink-0 text-sm font-semibold tabular-nums text-slate-700">
        {Math.round(contact.relevance)}
      </span>
    </button>
  );
}

/** One company's recommended roles: primary (highest relevance) + secondary (§21). */
export function CompanyRoleGroup({
  group,
  onOpen,
}: {
  group: CompanyContactGroup;
  onOpen: (c: ContactRecommendation) => void;
}) {
  const [primary, ...secondary] = group.recommendations;
  return (
    <Card>
      <div className="card-pad">
        <div className="flex items-center justify-between gap-3">
          <Link
            to={`/companies/${encodeURIComponent(group.company)}`}
            className="font-semibold text-slate-900 hover:text-brand-700"
            onClick={(e) => e.stopPropagation()}
          >
            {group.company}
          </Link>
          {group.industry && <span className="text-xs text-slate-400">{group.industry}</span>}
        </div>

        <div className="mt-3">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">Primary</p>
          <RoleRow contact={primary} onOpen={onOpen} />
        </div>

        {secondary.length > 0 && (
          <div className="mt-3">
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">Secondary</p>
            <div className="space-y-1">
              {secondary.map((c) => (
                <RoleRow key={c.id} contact={c} onOpen={onOpen} />
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
