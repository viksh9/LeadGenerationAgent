import type { LeadListParams, LeadPriority, LeadStatus, SignalType } from '@/types/lead';

export const PRIORITIES: LeadPriority[] = ['HOT', 'WARM', 'NURTURE', 'LOW'];

export const STATUSES: LeadStatus[] = [
  'NEW',
  'RESEARCHED',
  'CONTACTED',
  'REPLIED',
  'MEETING',
  'QUALIFIED',
  'PROPOSAL',
  'WON',
  'LOST',
  'NURTURE',
];

export const SIGNAL_TYPES: SignalType[] = [
  'HIRING',
  'PROJECT_AWARD',
  'PROJECT_EXECUTION',
  'EXPANSION',
  'DIGITAL_TRANSFORMATION',
  'TECHNOLOGY_INITIATIVE',
  'VENDOR_REQUIREMENT',
  'CONTRACT',
  'OTHER',
];

/** Readable labels for signal enums — never expose raw SCREAMING_CASE in the UI. */
export const SIGNAL_LABELS: Record<SignalType, string> = {
  HIRING: 'Hiring',
  PROJECT_AWARD: 'Project Award',
  PROJECT_EXECUTION: 'Project Execution',
  EXPANSION: 'Expansion',
  DIGITAL_TRANSFORMATION: 'Digital Transformation',
  TECHNOLOGY_INITIATIVE: 'Technology Initiative',
  VENDOR_REQUIREMENT: 'Vendor Requirement',
  CONTRACT: 'Contract',
  OTHER: 'Other',
};

export function humanizeSignal(value: SignalType | null | undefined): string {
  if (!value) return '—';
  return SIGNAL_LABELS[value] ?? value;
}

/** Suggested industry filter values (backend stores industry as free text). */
export const INDUSTRIES = ['IT', 'BFSI', 'FMCG', 'Healthcare'] as const;

export type SortBy = NonNullable<LeadListParams['sort_by']>;
export type SortOrder = NonNullable<LeadListParams['sort_order']>;

export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];
export const DEFAULT_PAGE_SIZE = 20;
