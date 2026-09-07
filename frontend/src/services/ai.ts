import { api } from './api';

/**
 * Thin API client + display helpers for the AI intelligence endpoints.
 *
 * These endpoints are grounded on real data. When no LLM provider is configured
 * (the normal state) the backend returns a *deterministic baseline* — honest,
 * rule-derived reasoning — rather than fabricated content. `ai_generated`
 * distinguishes a real LLM response from that deterministic baseline.
 */

/** How a single claim is grounded. FACT is source-backed; INFERENCE is reasoning. */
export type AIClaimType = 'FACT' | 'INFERENCE' | 'UNKNOWN';

export interface AIClaim {
  claim_text: string;
  claim_type: AIClaimType;
  support_level: string;
  evidence_ids: number[];
  validation_status: string | null;
}

export type AIAnalysisStatus =
  | 'DETERMINISTIC'
  | 'AI_VALIDATED'
  | 'AI_FLAGGED'
  | 'UNAVAILABLE'
  | 'ERROR';

export interface AIIntelligence {
  id: number | string;
  subject_type: string;
  subject_id: number | string;
  company_id: number | null;
  lead_id: number | null;
  executive_summary: string;
  opportunity_explanation: string;
  urgency_reason: string;
  business_problem_hypothesis: string;
  recommended_action: string;
  next_best_action: string;
  sales_angle: string;
  sales_pitch: string;
  verified_facts: AIClaim[];
  inferred_insights: AIClaim[];
  unknowns: string[];
  risk_flags: string[];
  target_roles: string[];
  evidence_ids: number[];
  source_ids: string[];
  confidence: number;
  analysis_status: AIAnalysisStatus;
  ai_generated: boolean;
  unsupported_claim_count: number;
  provider: string | null;
  model_name: string | null;
  prompt_version: string | null;
  generated_at: string | null;
}

export type AIProviderStatus =
  | 'NOT_CONFIGURED'
  | 'CONFIGURED'
  | 'CONNECTED'
  | 'AUTHENTICATION_FAILED'
  | 'RATE_LIMITED'
  | 'ERROR'
  | 'DISABLED';

export interface AIStatus {
  provider: string | null;
  model: string | null;
  status: AIProviderStatus;
  deterministic_baseline_available: boolean;
  note: string;
}

/** Lead AI intelligence (cached; a deterministic baseline is generated on first call). */
export async function fetchLeadAI(id: number, signal?: AbortSignal): Promise<AIIntelligence> {
  const { data } = await api.get<AIIntelligence>(`/leads/${id}/ai-intelligence`, { signal });
  return data;
}

/** Company AI intelligence (cached; deterministic baseline generated on first call). */
export async function fetchCompanyAI(id: number, signal?: AbortSignal): Promise<AIIntelligence> {
  const { data } = await api.get<AIIntelligence>(`/companies/${id}/ai-intelligence`, { signal });
  return data;
}

/** Current AI provider configuration/connectivity (GET /ai/status). */
export async function fetchAIStatus(signal?: AbortSignal): Promise<AIStatus> {
  const { data } = await api.get<AIStatus>('/ai/status', { signal });
  return data;
}

export interface AIDisplay {
  label: string;
  className: string;
}

const SLATE = 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';
const EMERALD = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
const AMBER = 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300';
const ROSE = 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300';
const BLUE = 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300';

const ANALYSIS_STATUS_DISPLAY: Record<AIAnalysisStatus, AIDisplay> = {
  DETERMINISTIC: { label: 'Deterministic', className: SLATE },
  AI_VALIDATED: { label: 'AI (validated)', className: EMERALD },
  AI_FLAGGED: { label: 'AI (claims flagged)', className: AMBER },
  UNAVAILABLE: { label: 'AI unavailable', className: SLATE },
  ERROR: { label: 'Error', className: ROSE },
};

/** Display label + honest Tailwind badge classes for an AI analysis status. */
export function analysisStatusDisplay(status: AIAnalysisStatus): AIDisplay {
  return ANALYSIS_STATUS_DISPLAY[status] ?? { label: status, className: SLATE };
}

const AI_PROVIDER_STATUS_DISPLAY: Record<AIProviderStatus, AIDisplay> = {
  CONNECTED: { label: 'Connected', className: EMERALD },
  CONFIGURED: { label: 'Configured', className: BLUE },
  NOT_CONFIGURED: { label: 'Not configured', className: SLATE },
  AUTHENTICATION_FAILED: { label: 'Authentication failed', className: ROSE },
  RATE_LIMITED: { label: 'Rate limited', className: AMBER },
  DISABLED: { label: 'Disabled', className: SLATE },
  ERROR: { label: 'Error', className: ROSE },
};

/** Display label + honest Tailwind badge classes for the AI provider status. */
export function aiProviderStatusDisplay(status: AIProviderStatus): AIDisplay {
  return AI_PROVIDER_STATUS_DISPLAY[status] ?? { label: status, className: SLATE };
}
