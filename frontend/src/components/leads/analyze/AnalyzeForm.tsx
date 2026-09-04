import type { FormEvent } from 'react';
import { Sparkles } from 'lucide-react';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import type { LeadAnalyzeRequest } from '@/types/lead';

interface AnalyzeFormProps {
  onAnalyze: (payload: LeadAnalyzeRequest) => void;
  isSubmitting: boolean;
}

function buildPayload(form: HTMLFormElement): LeadAnalyzeRequest {
  const data = new FormData(form);
  const str = (key: string) => {
    const value = ((data.get(key) as string | null) ?? '').trim();
    return value || undefined;
  };
  const num = (key: string) => {
    const value = str(key);
    return value === undefined ? undefined : Number(value);
  };
  const list = (key: string) => {
    const value = str(key);
    return value
      ? value
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean)
      : undefined;
  };
  const date = str('signal_date');

  return {
    company_name: str('company_name') ?? '',
    industry: str('industry'),
    location: str('location'),
    company_website: str('company_website'),
    signal_title: str('signal_title'),
    signal_description: str('signal_description'),
    signal_date: date ? new Date(date).toISOString() : undefined,
    source_name: str('source_name'),
    source_url: str('source_url'),
    technologies: list('technologies'),
    hiring_roles: list('hiring_roles'),
    estimated_hiring: num('estimated_hiring'),
    project_name: str('project_name'),
    project_value: num('project_value'),
    poc_title: str('poc_title'),
  };
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <fieldset className="card card-pad">
      <legend className="px-1 text-sm font-semibold text-slate-900">{title}</legend>
      <div className="mt-2 grid grid-cols-1 gap-3 sm:grid-cols-2">{children}</div>
    </fieldset>
  );
}

export function AnalyzeForm({ onAnalyze, isSubmitting }: AnalyzeFormProps) {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onAnalyze(buildPayload(event.currentTarget));
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Section title="Company">
        <Input label="Company name" name="company_name" required placeholder="NorthStar Banking Technologies" />
        <Input label="Industry" name="industry" placeholder="BFSI" />
        <Input label="Location" name="location" placeholder="Mumbai" />
        <Input label="Website" name="company_website" type="url" placeholder="https://…" />
      </Section>

      <Section title="Signal">
        <Input label="Signal title" name="signal_title" placeholder="Digital Banking Transformation" />
        <Input label="Signal date" name="signal_date" type="date" />
        <div className="sm:col-span-2">
          <label className="label" htmlFor="signal_description">
            Signal description
          </label>
          <textarea
            id="signal_description"
            name="signal_description"
            rows={4}
            className="input"
            placeholder="e.g. Won a modernization project and is hiring 30 Java engineers and 10 AWS engineers…"
          />
          <p className="mt-1 text-xs text-slate-400">
            The description drives signal detection — include roles, technologies, and hiring numbers.
          </p>
        </div>
        <Input label="Source name" name="source_name" placeholder="press release" />
        <Input label="Source URL" name="source_url" type="url" placeholder="https://…" />
      </Section>

      <Section title="Opportunity details (optional)">
        <Input label="Technologies (comma-separated)" name="technologies" placeholder="Java, AWS, DevOps" />
        <Input label="Hiring roles (comma-separated)" name="hiring_roles" placeholder="Java Engineer, AWS Engineer" />
        <Input label="Estimated hiring" name="estimated_hiring" type="number" min={0} placeholder="45" />
        <Input label="Project name" name="project_name" placeholder="Core Banking Revamp" />
        <Input label="Project value" name="project_value" type="number" min={0} placeholder="2500000" />
        <Input label="POC title" name="poc_title" placeholder="VP of Engineering" />
      </Section>

      <div className="flex justify-end">
        <Button type="submit" disabled={isSubmitting}>
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          {isSubmitting ? 'Analyzing…' : 'Analyze lead'}
        </Button>
      </div>
    </form>
  );
}
