import type { Lead, LeadPriority } from '@/types/lead';
import type {
  CompanyIntelligence,
  CompanyOpportunity,
  CompanyProject,
  CompanySignal,
  CompanySummary,
  CompanyTechnology,
  DecisionMakerRecommendation,
} from '@/types/company';

/**
 * Company Intelligence adapter.
 *
 * TEMPORARY STRATEGY (Phase 1/2): the backend has no company entity or company
 * endpoints, so company-level intelligence is derived here from Lead data,
 * grouped by `company_name`. When a real Company entity (company_id, domain,
 * employee_count, …) lands, only this file and the hooks change — the UI
 * components consume the typed shapes below and stay the same.
 *
 * Every value maps to a field that exists on a Lead. Nothing is invented.
 */

const PRIORITY_RANK: Record<LeadPriority, number> = { HOT: 3, WARM: 2, NURTURE: 1, LOW: 0 };

function topPriority(leads: Lead[]): LeadPriority {
  return leads.reduce<LeadPriority>(
    (best, lead) => (PRIORITY_RANK[lead.lead_priority] > PRIORITY_RANK[best] ? lead.lead_priority : best),
    'LOW',
  );
}

function unionStrings(values: (string | null | undefined)[][]): string[] {
  const out: string[] = [];
  for (const arr of values) {
    for (const v of arr) {
      if (v && !out.includes(v)) out.push(v);
    }
  }
  return out;
}

function latestSignalDate(leads: Lead[]): string | null {
  return leads.reduce<string | null>((latest, lead) => {
    if (lead.signal_date && (!latest || lead.signal_date > latest)) return lead.signal_date;
    return latest;
  }, null);
}

/** First non-null value of a field across leads (leads arrive score-desc). */
function firstNonNull<T>(leads: Lead[], pick: (lead: Lead) => T | null | undefined): T | null {
  for (const lead of leads) {
    const v = pick(lead);
    if (v != null && v !== '') return v;
  }
  return null;
}

/** Group all leads into per-company summaries (used by the Companies list). */
export function buildCompanySummaries(leads: Lead[]): CompanySummary[] {
  const groups = new Map<string, Lead[]>();
  for (const lead of leads) {
    const existing = groups.get(lead.company_name);
    if (existing) existing.push(lead);
    else groups.set(lead.company_name, [lead]);
  }

  const summaries = Array.from(groups.entries()).map(([name, groupLeads]) =>
    summarize(name, groupLeads),
  );
  return summaries.sort((a, b) => b.bestScore - a.bestScore);
}

function summarize(name: string, leads: Lead[]): CompanySummary {
  const technologies = unionStrings(leads.map((l) => l.technologies ?? []));
  const latest = latestSignalDate(leads);
  const latestLead = latest ? leads.find((l) => l.signal_date === latest) ?? null : null;
  return {
    name,
    industry: firstNonNull(leads, (l) => l.industry),
    location: firstNonNull(leads, (l) => l.location),
    companySize: firstNonNull(leads, (l) => l.company_size),
    website: firstNonNull(leads, (l) => l.company_website),
    leadCount: leads.length,
    bestScore: leads.reduce((max, l) => Math.max(max, l.lead_score), 0),
    topPriority: topPriority(leads),
    technologies,
    estimatedHiring: leads.reduce((sum, l) => sum + (l.estimated_hiring ?? 0), 0),
    latestSignal: latest,
    totalSignals: leads.filter((l) => l.signal_type).length,
    latestSignalType: latestLead?.signal_type ?? null,
  };
}

/** Build the full intelligence profile for a single company from its leads. */
export function buildCompanyIntelligence(name: string, leads: Lead[]): CompanyIntelligence {
  const summary = summarize(name, leads);

  // Technology landscape with frequency, most common first.
  const techCounts = new Map<string, number>();
  for (const lead of leads) {
    for (const tech of lead.technologies ?? []) {
      techCounts.set(tech, (techCounts.get(tech) ?? 0) + 1);
    }
  }
  const technologyLandscape: CompanyTechnology[] = Array.from(techCounts.entries())
    .map(([name, leadCount]) => ({ name, leadCount }))
    .sort((a, b) => b.leadCount - a.leadCount || a.name.localeCompare(b.name));

  // Signal timeline, newest first.
  const signals: CompanySignal[] = leads
    .filter((l) => l.signal_type || l.signal_title)
    .map((l) => ({
      leadId: l.id,
      signalType: l.signal_type,
      title: l.signal_title,
      description: l.signal_description,
      date: l.signal_date,
      confidence: l.signal_confidence,
      score: l.lead_score,
    }))
    .sort((a, b) => (b.date ?? '').localeCompare(a.date ?? ''));

  // Opportunities (structured staffing/urgency are not persisted).
  const opportunities: CompanyOpportunity[] = leads
    .filter((l) => l.opportunity_summary || l.estimated_hiring)
    .map((l) => ({
      leadId: l.id,
      summary: l.opportunity_summary,
      estimatedHiring: l.estimated_hiring,
      score: l.lead_score,
      priority: l.lead_priority,
      status: l.status,
    }))
    .sort((a, b) => b.score - a.score);

  // Projects.
  const projects: CompanyProject[] = leads
    .filter((l) => l.project_name)
    .map((l) => ({
      leadId: l.id,
      name: l.project_name as string,
      value: l.project_value,
      date: l.signal_date,
      signalType: l.signal_type,
      opportunitySummary: l.opportunity_summary,
    }));

  // Decision-maker roles aggregated across leads (dedupe by role/title).
  const dmMap = new Map<string, DecisionMakerRecommendation>();
  for (const lead of leads) {
    const role = lead.poc_title || (lead.poc_name ? 'Contact' : null);
    if (!role) continue;
    const existing = dmMap.get(role);
    if (existing) {
      existing.leadCount += 1;
      existing.name ??= lead.poc_name;
      existing.linkedinUrl ??= lead.poc_linkedin_url;
    } else {
      dmMap.set(role, {
        role,
        name: lead.poc_name,
        linkedinUrl: lead.poc_linkedin_url,
        leadCount: 1,
      });
    }
  }
  const decisionMakers = Array.from(dmMap.values()).sort((a, b) => b.leadCount - a.leadCount);

  // Evidence, one record per lead that has a source.
  const evidence = leads
    .filter((l) => l.source_name || l.source_url)
    .map((l) => ({
      leadId: l.id,
      sourceName: l.source_name,
      sourceUrl: l.source_url,
      signalDate: l.signal_date,
      lastVerified: l.last_verified_at,
      confidence: l.signal_confidence,
    }));

  // Contacts (named people only).
  const seenContacts = new Set<string>();
  const contacts = leads
    .filter((l) => l.poc_name && !seenContacts.has(l.poc_name) && seenContacts.add(l.poc_name))
    .map((l) => ({ name: l.poc_name as string, title: l.poc_title, linkedinUrl: l.poc_linkedin_url }));

  const hiring = {
    estimatedHiring: leads.reduce((sum, l) => sum + (l.estimated_hiring ?? 0), 0),
    maxEstimatedHiring: leads.reduce((max, l) => Math.max(max, l.estimated_hiring ?? 0), 0),
    roles: unionStrings(leads.map((l) => l.hiring_roles ?? [])),
    technologies: summary.technologies,
  };

  // Recommended action: strongest lead's recommendation, else a monitoring hint.
  const strongest = [...leads].sort((a, b) => b.lead_score - a.lead_score)[0];
  const recommendedAction =
    strongest?.recommended_action ||
    'Monitor the account for stronger project or hiring signals before qualification.';

  const metrics = {
    totalLeads: leads.length,
    hotLeads: leads.filter((l) => l.lead_priority === 'HOT').length,
    warmLeads: leads.filter((l) => l.lead_priority === 'WARM').length,
    totalSignals: summary.totalSignals,
    latestSignalDate: summary.latestSignal,
    highestLeadScore: summary.bestScore,
    technologyCount: technologyLandscape.length,
    opportunityCount: opportunities.length,
  };

  return {
    ...summary,
    metrics,
    technologyLandscape,
    signals,
    opportunities,
    projects,
    decisionMakers,
    evidence,
    hiring,
    recommendedAction,
    contacts,
    leads: [...leads].sort((a, b) => b.lead_score - a.lead_score),
  };
}
