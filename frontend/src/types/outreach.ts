import type { LeadPriority, LeadStatus, SignalType } from './lead';
import type { OpportunityType, StaffingNeed, Urgency } from './opportunity';

/**
 * Outreach items are derived from Lead data (no backend Outreach entity). The
 * backend persists a single `recommended_pitch` (email-style, usually starting
 * with a "Subject:" line). The per-channel LinkedIn message, call talking
 * points, pitch confidence, and message strategy produced at analysis time are
 * NOT persisted — they are shown as unavailable, never fabricated. Message
 * status is a documented FRONTEND preparation status derived from the related
 * lead status; there is no persisted outreach lifecycle yet.
 */

export type MessageChannel = 'email' | 'linkedin' | 'call';

/** Frontend preparation status (not persisted — see §8 / docs). */
export type OutreachStatus =
  | 'DRAFT'
  | 'READY'
  | 'REVIEWED'
  | 'CONTACTED'
  | 'RESPONDED'
  | 'MEETING'
  | 'FOLLOW_UP'
  | 'COMPLETED';

export type MessageStrategy =
  | 'PROJECT_RAMP_UP'
  | 'STAFF_AUGMENTATION'
  | 'VENDOR_OPPORTUNITY'
  | 'DIGITAL_TRANSFORMATION'
  | 'TECHNOLOGY_IMPLEMENTATION'
  | 'NORMAL_HIRING'
  | 'NURTURE';

/** The generated messaging for an item (persisted parts only). */
export interface OutreachMessage {
  subject: string | null;
  body: string; // pitch body
  pitch: string; // full recommended_pitch
  linkedin: string | null; // not persisted -> null
  talkingPoints: string[]; // not persisted -> []
}

export interface OutreachItem {
  leadId: number;
  company: string;
  industry: string | null;
  role: string | null; // target decision-maker role (poc_title)

  message: OutreachMessage;
  recommendedAction: string | null;
  messageStrategy: MessageStrategy;
  pitchConfidence: number | null; // not persisted -> null

  // Opportunity context
  opportunityType: OpportunityType;
  opportunitySummary: string | null;
  staffingNeed: StaffingNeed;
  urgency: Urgency;
  urgencyReason: string | null;
  estimatedHiring: number | null;
  technologies: string[];

  priority: LeadPriority;
  score: number;
  status: OutreachStatus; // derived preparation status
  leadStatus: LeadStatus; // the underlying persisted lead status

  // Evidence
  signalType: SignalType | null;
  signalTitle: string | null;
  signalDate: string | null;
  sourceName: string | null;
  sourceUrl: string | null;
  signalConfidence: number | null;
  updatedAt: string | null;

  // Queue classification
  ready: boolean;
  reviewReasons: string[];
}

export interface OutreachSummary {
  ready: number;
  needsReview: number;
  hot: number;
  inProgress: number;
}

export type OutreachSortBy = 'priority' | 'score' | 'company' | 'opportunity' | 'created' | 'signal_date';

export interface OutreachFilterState {
  search: string;
  priority: LeadPriority | '';
  industry: string;
  opportunityType: OpportunityType | '';
  role: string;
  status: OutreachStatus | '';
  minScore: string;
}
