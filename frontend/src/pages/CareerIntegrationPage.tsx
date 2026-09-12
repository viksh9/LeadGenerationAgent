import { useState, type FormEvent } from 'react';
import { Radar, CheckCircle2, XCircle, ShieldCheck } from 'lucide-react';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { ExternalLinkValue } from '@/components/leads/detail/primitives';
import { useDiscoverCareerSource } from '@/hooks/useCareerSources';
import { providerLabel } from '@/services/careerSources';

const EMERALD = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
const SLATE = 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-800 dark:text-slate-200">{children ?? '—'}</dd>
    </div>
  );
}

/**
 * Career Integration — discover a company's official ATS / career source from a
 * domain or careers URL you provide. This is a LIVE, SSRF-safe probe of that
 * domain; the result is real (a Greenhouse/Lever board id when found, otherwise
 * "not found") and nothing is fabricated or stored.
 */
export function CareerIntegrationPage() {
  const [companyName, setCompanyName] = useState('');
  const [domainOrUrl, setDomainOrUrl] = useState('');
  const discover = useDiscoverCareerSource();
  const result = discover.data;

  const looksLikeUrl = /^https?:\/\//i.test(domainOrUrl.trim());
  const canSubmit = companyName.trim().length > 0 && domainOrUrl.trim().length > 0 && !discover.isPending;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    const value = domainOrUrl.trim();
    discover.mutate({
      company_name: companyName,
      ...(looksLikeUrl ? { careers_url: value } : { domain: value }),
    });
  };

  return (
    <PageContainer
      title="Career Integration"
      subtitle="Discover a company's official ATS / career source (Greenhouse or Lever) from its domain or careers URL — a live, verified check."
    >
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardTitle>Discover a source</CardTitle>
          <form className="mt-4 space-y-4" onSubmit={onSubmit}>
            <Input
              label="Company name"
              placeholder="e.g. EPAM Systems"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              autoComplete="off"
            />
            <Input
              label="Official domain or careers URL"
              placeholder="e.g. epam.com  or  https://careers.epam.com"
              value={domainOrUrl}
              onChange={(e) => setDomainOrUrl(e.target.value)}
              autoComplete="off"
            />
            <p className="text-xs text-slate-400 dark:text-slate-500">
              We probe the domain you provide (safely) and report the real result. Only
              Greenhouse and Lever are auto-detected; a board id is never guessed.
            </p>
            <Button type="submit" disabled={!canSubmit}>
              <Radar className={discover.isPending ? 'h-4 w-4 animate-spin' : 'h-4 w-4'} aria-hidden="true" />
              {discover.isPending ? 'Discovering…' : 'Discover'}
            </Button>
          </form>
        </Card>

        <Card>
          <CardTitle>Result</CardTitle>
          {!result && !discover.isPending && (
            <p className="mt-4 text-sm text-slate-400 dark:text-slate-500">
              Enter a company and its domain or careers URL, then run a discovery.
            </p>
          )}
          {discover.isPending && (
            <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">Probing the domain…</p>
          )}
          {result && !discover.isPending && (
            <div className="mt-4 space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                {result.found ? (
                  <span className={`badge ${EMERALD}`}>
                    <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" /> Source found
                  </span>
                ) : (
                  <span className={`badge ${SLATE}`}>
                    <XCircle className="h-3.5 w-3.5" aria-hidden="true" /> No source found
                  </span>
                )}
                {result.found && result.verified && (
                  <span className={`badge ${EMERALD}`}>
                    <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" /> Ownership verified
                  </span>
                )}
              </div>

              <dl className="grid grid-cols-2 gap-3">
                <Field label="Company">{result.company_name}</Field>
                <Field label="ATS provider">
                  {result.provider ? providerLabel(result.provider) : '—'}
                </Field>
                <Field label="Board identifier">{result.board_identifier}</Field>
                <Field label="Discovery method">{result.discovery_method}</Field>
                <Field label="Careers URL">
                  <ExternalLinkValue href={result.careers_url} stripScheme />
                </Field>
              </dl>

              <p className="text-sm text-slate-600 dark:text-slate-300">{result.detail}</p>
            </div>
          )}
        </Card>
      </div>
    </PageContainer>
  );
}
