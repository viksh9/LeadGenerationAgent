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

export type SortBy = NonNullable<LeadListParams['sort_by']>;
export type SortOrder = NonNullable<LeadListParams['sort_order']>;

export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];
export const DEFAULT_PAGE_SIZE = 20;
