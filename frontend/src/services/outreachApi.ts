import { api } from './api';

/**
 * Thin API client + display helpers for the REAL outreach-draft lifecycle
 * (generate → review → approve → send). This is distinct from the derived,
 * client-side "prep" adapter in services/outreach.ts — that one shapes leads
 * into a copy-only view, while this file talks to the persisted draft endpoints
 * and the live email/CRM provider status.
 *
 * A draft is only ever "sent" when the backend returns status === "SENT". The
 * UI never implies a message went out otherwise, and a draft that is not
 * evidence-grounded (grounding_ok === false) cannot be approved.
 */

export type OutreachChannel = 'EMAIL' | 'LINKEDIN' | 'CALL';

export type OutreachDraftStatus =
  | 'DRAFT'
  | 'READY_FOR_REVIEW'
  | 'APPROVED'
  | 'SENT'
  | 'CANCELLED'
  | 'FAILED';

export interface OutreachDraft {
  id: number;
  lead_id?: number | null;
  company_id?: number | null;
  contact_id?: number | null;
  target_role?: string | null;
  channel: OutreachChannel;
  subject?: string | null;
  message?: string | null;
  evidence_ids: number[];
  ai_generated: boolean;
  grounding_ok: boolean;
  confidence: number;
  status: OutreachDraftStatus;
  recipient_email?: string | null;
  provider?: string | null;
  provider_message_id?: string | null;
  error?: string | null;
  created_by: string;
  approved_by?: string | null;
  created_at: string;
  approved_at?: string | null;
  sent_at?: string | null;
}

export interface OutreachDraftList {
  items: OutreachDraft[];
  total: number;
}

export type EmailProviderStatus = 'CONFIGURED' | 'NOT_CONFIGURED' | 'ERROR' | string;

export interface ProviderStatus {
  email_provider?: string | null;
  email_status: EmailProviderStatus;
  email_from?: string | null;
  crm_provider: string;
  crm_status: string;
  webhook_configured: boolean;
  note: string;
}

export interface DraftListParams {
  status?: OutreachDraftStatus;
  limit?: number;
  offset?: number;
}

export interface GenerateDraftBody {
  lead_id: number;
  channel?: OutreachChannel;
  contact_id?: number;
}

export interface EditDraftBody {
  subject?: string;
  message?: string;
}

// --- Fetchers --------------------------------------------------------------

/** Real persisted outreach drafts, optionally filtered (GET /outreach/drafts). */
export async function fetchDrafts(
  params: DraftListParams = {},
  signal?: AbortSignal,
): Promise<OutreachDraftList> {
  const { data } = await api.get<OutreachDraftList>('/outreach/drafts', { params, signal });
  return data;
}

/** A single outreach draft (GET /outreach/drafts/{id}). */
export async function fetchDraft(id: number, signal?: AbortSignal): Promise<OutreachDraft> {
  const { data } = await api.get<OutreachDraft>(`/outreach/drafts/${id}`, { signal });
  return data;
}

/** Generate a new draft for a lead (POST /outreach/drafts). */
export async function generateDraft(body: GenerateDraftBody): Promise<OutreachDraft> {
  const { data } = await api.post<OutreachDraft>('/outreach/drafts', body);
  return data;
}

/** Edit a draft's subject/message (PUT /outreach/drafts/{id}). */
export async function editDraft(id: number, body: EditDraftBody): Promise<OutreachDraft> {
  const { data } = await api.put<OutreachDraft>(`/outreach/drafts/${id}`, body);
  return data;
}

/** Approve a draft (POST /outreach/drafts/{id}/approve). */
export async function approveDraft(id: number): Promise<OutreachDraft> {
  const { data } = await api.post<OutreachDraft>(`/outreach/drafts/${id}/approve`);
  return data;
}

/** Cancel a draft (POST /outreach/drafts/{id}/cancel). */
export async function cancelDraft(id: number): Promise<OutreachDraft> {
  const { data } = await api.post<OutreachDraft>(`/outreach/drafts/${id}/cancel`);
  return data;
}

/**
 * Send an APPROVED draft (POST /outreach/{id}/send). The backend returns 422 if
 * the draft is not APPROVED, has no verified email, or the provider is not
 * configured. The returned draft is only "sent" when status === "SENT".
 */
export async function sendDraft(id: number): Promise<OutreachDraft> {
  const { data } = await api.post<OutreachDraft>(`/outreach/${id}/send`);
  return data;
}

/** Live email/CRM provider status (GET /outreach/providers/status). */
export async function fetchProviderStatus(signal?: AbortSignal): Promise<ProviderStatus> {
  const { data } = await api.get<ProviderStatus>('/outreach/providers/status', { signal });
  return data;
}

// --- Display helpers -------------------------------------------------------

export interface DraftDisplay {
  label: string;
  className: string;
}

const EMERALD = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
const BLUE = 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300';
const AMBER = 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300';
const ROSE = 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300';
const SLATE = 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';

const DRAFT_STATUS_DISPLAY: Record<OutreachDraftStatus, DraftDisplay> = {
  DRAFT: { label: 'Draft', className: SLATE },
  READY_FOR_REVIEW: { label: 'Ready for review', className: AMBER },
  APPROVED: { label: 'Approved', className: BLUE },
  SENT: { label: 'Sent', className: EMERALD },
  CANCELLED: { label: 'Cancelled', className: SLATE },
  FAILED: { label: 'Failed', className: ROSE },
};

/** Display label + honest Tailwind badge classes for an outreach draft status. */
export function draftStatusDisplay(status: OutreachDraftStatus): DraftDisplay {
  return DRAFT_STATUS_DISPLAY[status] ?? { label: status, className: SLATE };
}
