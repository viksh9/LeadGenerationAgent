import { api } from './api';

/**
 * Thin API client + display helpers for the CRM / sales-pipeline lifecycle.
 *
 * Every record here is real: lead status transitions, logged CRM activities,
 * the activity timeline, sales opportunities and follow-up tasks are all
 * persisted by the backend. Nothing on these endpoints is fabricated, and the
 * display helpers below never invent a number — an unavailable pipeline value
 * or an insufficient-data conversion rate is rendered honestly as such.
 */

// --- Enums (exact server values) -------------------------------------------

export type ActivityType =
  | 'NOTE'
  | 'EMAIL'
  | 'EMAIL_REPLY'
  | 'CALL'
  | 'MEETING'
  | 'LINKEDIN_MESSAGE'
  | 'LINKEDIN_REPLY'
  | 'TASK'
  | 'STATUS_CHANGE'
  | 'RESEARCH'
  | 'OTHER';

export type ActivityStatus =
  | 'PLANNED'
  | 'ATTEMPTED'
  | 'SENT'
  | 'DELIVERED'
  | 'REPLIED'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export type ActivityDirection = 'INBOUND' | 'OUTBOUND' | 'INTERNAL';

export type SalesStage =
  | 'IDENTIFIED'
  | 'RESEARCHED'
  | 'OUTREACH_READY'
  | 'CONTACTED'
  | 'ENGAGED'
  | 'QUALIFIED'
  | 'DISCOVERY'
  | 'PROPOSAL'
  | 'NEGOTIATION'
  | 'WON'
  | 'LOST'
  | 'NURTURE';

export type FollowUpTaskType =
  | 'REVIEW_REPLY'
  | 'PREPARE_PROPOSAL'
  | 'FOLLOW_UP'
  | 'CHECK_TENDER_DEADLINE'
  | 'RESEARCH_DECISION_MAKER'
  | 'REVIEW_LEAD'
  | 'OTHER';

export type FollowUpStatus = 'OPEN' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED' | 'SNOOZED';

export type ValueSource = 'USER' | 'EVIDENCE' | 'NOT_AVAILABLE';

// --- Types (exact server field names) --------------------------------------

export interface CRMActivity {
  id: number;
  lead_id?: number | null;
  company_id?: number | null;
  contact_id?: number | null;
  opportunity_id?: number | null;
  activity_type: ActivityType;
  direction: ActivityDirection;
  subject?: string | null;
  body_reference?: string | null;
  status: ActivityStatus;
  source?: string | null;
  external_id?: string | null;
  is_system_event: boolean;
  occurred_at: string;
  created_by: string;
}

export interface CRMActivityList {
  items: CRMActivity[];
  total: number;
}

export interface LeadStatusHistory {
  id: number;
  lead_id: number;
  old_status?: string | null;
  new_status: string;
  changed_by: string;
  reason?: string | null;
  source?: string | null;
  created_at: string;
}

export interface NextBestAction {
  lead_id: number;
  next_best_action: string;
}

export interface TimelineItem {
  kind: 'SYSTEM_EVENT' | 'HUMAN_ACTIVITY';
  category: string;
  event_type: string;
  title: string;
  detail?: string | null;
  occurred_at: string;
  source?: string | null;
}

export interface LeadTimeline {
  lead_id: number;
  items: TimelineItem[];
  total: number;
}

export interface SalesOpportunity {
  id: number;
  company_id?: number | null;
  lead_id?: number | null;
  opportunity_candidate_id?: number | null;
  opportunity_type?: string | null;
  title: string;
  description?: string | null;
  estimated_team_scale?: string | null;
  estimated_value: number | null;
  estimated_value_currency?: string | null;
  value_source: ValueSource;
  confidence: number;
  evidence_ids: number[];
  stage: SalesStage;
  probability: number | null;
  expected_close_date?: string | null;
  owner?: string | null;
  created_at: string;
  updated_at: string;
}

export interface SalesOpportunityList {
  items: SalesOpportunity[];
  total: number;
}

export interface PipelineColumn {
  stage: SalesStage;
  count: number;
  opportunities: SalesOpportunity[];
}

export interface PipelineBoard {
  columns: PipelineColumn[];
  total: number;
}

export interface FollowUpTask {
  id: number;
  lead_id?: number | null;
  contact_id?: number | null;
  company_id?: number | null;
  due_at?: string | null;
  task_type: FollowUpTaskType;
  title: string;
  reason?: string | null;
  status: FollowUpStatus;
  created_by: string;
  created_at: string;
  completed_at?: string | null;
}

export interface FollowUpTaskList {
  items: FollowUpTask[];
  total: number;
}

export interface ConversionMetric {
  label: string;
  numerator: number;
  denominator: number;
  rate: number | 'INSUFFICIENT_DATA';
}

export interface CRMAnalytics {
  generated_at: string;
  total_leads: number;
  lead_status_counts: Record<string, number>;
  sales_stage_counts: Record<string, number>;
  activity_counts: Record<string, number>;
  real_contacted: number;
  real_replies: number;
  real_meetings: number;
  conversion: ConversionMetric[];
  pipeline_value: number | 'NOT_AVAILABLE';
  pipeline_value_currency?: string | null;
  pipeline_value_opportunities: number;
  open_opportunities: number;
  won: number;
  lost: number;
}

// --- Request bodies --------------------------------------------------------

export interface TransitionLeadBody {
  new_status: string;
  reason?: string;
}

export interface CreateActivityBody {
  activity_type: ActivityType;
  lead_id?: number;
  company_id?: number;
  contact_id?: number;
  opportunity_id?: number;
  subject?: string;
  body_reference?: string;
}

export interface CreateSalesOpportunityBody {
  title: string;
  company_id?: number;
  lead_id?: number;
  opportunity_type?: string;
  description?: string;
  estimated_team_scale?: string;
  estimated_value?: number;
  estimated_value_currency?: string;
  value_source?: ValueSource;
}

export interface SetOpportunityStageBody {
  stage: SalesStage;
  reason?: string;
}

export interface SalesOpportunityParams {
  stage?: SalesStage;
  company_id?: number;
  limit?: number;
  offset?: number;
}

export interface FollowUpParams {
  status?: FollowUpStatus;
  lead_id?: number;
}

// --- Fetchers --------------------------------------------------------------

/** Transition a lead to a new CRM status (POST /leads/{id}/transition). */
export async function transitionLead(
  id: number,
  body: TransitionLeadBody,
): Promise<LeadStatusHistory> {
  const { data } = await api.post<LeadStatusHistory>(`/leads/${id}/transition`, body);
  return data;
}

/** A lead's full status history (GET /leads/{id}/status-history). */
export async function fetchStatusHistory(
  id: number,
  signal?: AbortSignal,
): Promise<LeadStatusHistory[]> {
  const { data } = await api.get<LeadStatusHistory[]>(`/leads/${id}/status-history`, { signal });
  return data;
}

/** The recommended next action for a lead (GET /leads/{id}/next-best-action). */
export async function fetchNextBestAction(
  id: number,
  signal?: AbortSignal,
): Promise<NextBestAction> {
  const { data } = await api.get<NextBestAction>(`/leads/${id}/next-best-action`, { signal });
  return data;
}

/** Logged CRM activities for a lead (GET /leads/{id}/activities). */
export async function fetchLeadActivities(
  id: number,
  signal?: AbortSignal,
): Promise<CRMActivityList> {
  const { data } = await api.get<CRMActivityList>(`/leads/${id}/activities`, { signal });
  return data;
}

/** Log a new CRM activity (POST /activities). */
export async function createActivity(body: CreateActivityBody): Promise<CRMActivity> {
  const { data } = await api.post<CRMActivity>('/activities', body);
  return data;
}

/** The merged system-event + human-activity timeline (GET /leads/{id}/timeline). */
export async function fetchLeadTimeline(id: number, signal?: AbortSignal): Promise<LeadTimeline> {
  const { data } = await api.get<LeadTimeline>(`/leads/${id}/timeline`, { signal });
  return data;
}

/** Sales opportunities, optionally filtered (GET /sales-opportunities). */
export async function fetchSalesOpportunities(
  params: SalesOpportunityParams = {},
  signal?: AbortSignal,
): Promise<SalesOpportunityList> {
  const { data } = await api.get<SalesOpportunityList>('/sales-opportunities', { params, signal });
  return data;
}

/** The pipeline Kanban board grouped by stage (GET /pipeline/board). */
export async function fetchPipelineBoard(signal?: AbortSignal): Promise<PipelineBoard> {
  const { data } = await api.get<PipelineBoard>('/pipeline/board', { signal });
  return data;
}

/** Create a sales opportunity (POST /sales-opportunities). */
export async function createSalesOpportunity(
  body: CreateSalesOpportunityBody,
): Promise<SalesOpportunity> {
  const { data } = await api.post<SalesOpportunity>('/sales-opportunities', body);
  return data;
}

/** Move an opportunity to a new stage (POST /sales-opportunities/{id}/stage). */
export async function setOpportunityStage(
  id: number,
  body: SetOpportunityStageBody,
): Promise<SalesOpportunity> {
  const { data } = await api.post<SalesOpportunity>(`/sales-opportunities/${id}/stage`, body);
  return data;
}

/** Promote a candidate into a real sales opportunity (POST /opportunity-candidates/{id}/promote). */
export async function promoteCandidate(id: number): Promise<SalesOpportunity> {
  const { data } = await api.post<SalesOpportunity>(`/opportunity-candidates/${id}/promote`);
  return data;
}

/** Follow-up tasks, optionally filtered (GET /follow-ups). */
export async function fetchFollowUps(
  params: FollowUpParams = {},
  signal?: AbortSignal,
): Promise<FollowUpTaskList> {
  const { data } = await api.get<FollowUpTaskList>('/follow-ups', { params, signal });
  return data;
}

/** Transition a follow-up task's status (POST /follow-ups/{id}/status). */
export async function setFollowUpStatus(
  id: number,
  status: FollowUpStatus,
): Promise<FollowUpTask> {
  const { data } = await api.post<FollowUpTask>(`/follow-ups/${id}/status`, { status });
  return data;
}

/** Real CRM analytics — counts, funnel and pipeline value (GET /crm/analytics). */
export async function fetchCrmAnalytics(signal?: AbortSignal): Promise<CRMAnalytics> {
  const { data } = await api.get<CRMAnalytics>('/crm/analytics', { signal });
  return data;
}

// --- Display helpers -------------------------------------------------------

export interface CrmDisplay {
  label: string;
  className: string;
}

const EMERALD = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
const BLUE = 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300';
const AMBER = 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300';
const ROSE = 'bg-rose-100 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300';
const SLATE = 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';

const ACTIVITY_TYPE_DISPLAY: Record<ActivityType, CrmDisplay> = {
  NOTE: { label: 'Note', className: SLATE },
  EMAIL: { label: 'Email', className: BLUE },
  EMAIL_REPLY: { label: 'Email reply', className: EMERALD },
  CALL: { label: 'Call', className: BLUE },
  MEETING: { label: 'Meeting', className: EMERALD },
  LINKEDIN_MESSAGE: { label: 'LinkedIn message', className: BLUE },
  LINKEDIN_REPLY: { label: 'LinkedIn reply', className: EMERALD },
  TASK: { label: 'Task', className: AMBER },
  STATUS_CHANGE: { label: 'Status change', className: SLATE },
  RESEARCH: { label: 'Research', className: SLATE },
  OTHER: { label: 'Other', className: SLATE },
};

export function activityTypeDisplay(type: ActivityType): CrmDisplay {
  return ACTIVITY_TYPE_DISPLAY[type] ?? { label: type, className: SLATE };
}

const ACTIVITY_STATUS_DISPLAY: Record<ActivityStatus, CrmDisplay> = {
  PLANNED: { label: 'Planned', className: SLATE },
  ATTEMPTED: { label: 'Attempted', className: AMBER },
  SENT: { label: 'Sent', className: BLUE },
  DELIVERED: { label: 'Delivered', className: BLUE },
  REPLIED: { label: 'Replied', className: EMERALD },
  COMPLETED: { label: 'Completed', className: EMERALD },
  FAILED: { label: 'Failed', className: ROSE },
  CANCELLED: { label: 'Cancelled', className: SLATE },
};

export function activityStatusDisplay(status: ActivityStatus): CrmDisplay {
  return ACTIVITY_STATUS_DISPLAY[status] ?? { label: status, className: SLATE };
}

const SALES_STAGE_DISPLAY: Record<SalesStage, CrmDisplay> = {
  IDENTIFIED: { label: 'Identified', className: SLATE },
  RESEARCHED: { label: 'Researched', className: SLATE },
  OUTREACH_READY: { label: 'Outreach ready', className: BLUE },
  CONTACTED: { label: 'Contacted', className: BLUE },
  ENGAGED: { label: 'Engaged', className: BLUE },
  QUALIFIED: { label: 'Qualified', className: AMBER },
  DISCOVERY: { label: 'Discovery', className: AMBER },
  PROPOSAL: { label: 'Proposal', className: AMBER },
  NEGOTIATION: { label: 'Negotiation', className: AMBER },
  WON: { label: 'Won', className: EMERALD },
  LOST: { label: 'Lost', className: ROSE },
  NURTURE: { label: 'Nurture', className: SLATE },
};

export function salesStageDisplay(stage: SalesStage): CrmDisplay {
  return SALES_STAGE_DISPLAY[stage] ?? { label: stage, className: SLATE };
}

/** Every sales stage in pipeline order — for stage selects and board fallbacks. */
export const SALES_STAGES: SalesStage[] = [
  'IDENTIFIED',
  'RESEARCHED',
  'OUTREACH_READY',
  'CONTACTED',
  'ENGAGED',
  'QUALIFIED',
  'DISCOVERY',
  'PROPOSAL',
  'NEGOTIATION',
  'WON',
  'LOST',
  'NURTURE',
];

const FOLLOW_UP_STATUS_DISPLAY: Record<FollowUpStatus, CrmDisplay> = {
  OPEN: { label: 'Open', className: BLUE },
  IN_PROGRESS: { label: 'In progress', className: AMBER },
  COMPLETED: { label: 'Completed', className: EMERALD },
  CANCELLED: { label: 'Cancelled', className: SLATE },
  SNOOZED: { label: 'Snoozed', className: SLATE },
};

export function followUpStatusDisplay(status: FollowUpStatus): CrmDisplay {
  return FOLLOW_UP_STATUS_DISPLAY[status] ?? { label: status, className: SLATE };
}

const FOLLOW_UP_TYPE_LABELS: Record<FollowUpTaskType, string> = {
  REVIEW_REPLY: 'Review reply',
  PREPARE_PROPOSAL: 'Prepare proposal',
  FOLLOW_UP: 'Follow up',
  CHECK_TENDER_DEADLINE: 'Check tender deadline',
  RESEARCH_DECISION_MAKER: 'Research decision maker',
  REVIEW_LEAD: 'Review lead',
  OTHER: 'Other',
};

export function followUpTypeLabel(type: FollowUpTaskType): string {
  return FOLLOW_UP_TYPE_LABELS[type] ?? type;
}

// --- Honest formatters -----------------------------------------------------

/**
 * Format a pipeline / opportunity value. A `"NOT_AVAILABLE"` sentinel or a
 * null/undefined value renders the honest string "Not available" — never a
 * fabricated ₹0. A real number is formatted with the currency when provided.
 */
export function formatPipelineValue(
  value: number | 'NOT_AVAILABLE' | null | undefined,
  currency?: string | null,
): string {
  if (value === null || value === undefined || value === 'NOT_AVAILABLE') {
    return 'Not available';
  }
  if (currency) {
    try {
      return new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency,
        maximumFractionDigits: 0,
      }).format(value);
    } catch {
      // Unknown currency code — fall through to a plain grouped number + code.
      return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value)} ${currency}`;
    }
  }
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(value);
}

/**
 * Format a conversion rate. The `"INSUFFICIENT_DATA"` sentinel renders as
 * "Insufficient data" — never as 0% or a made-up percentage. A numeric rate is
 * treated as a fraction (0–1) and rendered as a percentage.
 */
export function formatRate(rate: number | 'INSUFFICIENT_DATA' | null | undefined): string {
  if (rate === 'INSUFFICIENT_DATA' || rate === null || rate === undefined) {
    return 'Insufficient data';
  }
  const pct = rate * 100;
  const rounded = Math.round(pct * 10) / 10;
  return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(1)}%`;
}
