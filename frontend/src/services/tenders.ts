import { api } from './api';

/**
 * A public tender / procurement opportunity from the backend (GET /tenders).
 * Every field maps to a real collected record. estimated_value stays nullable so
 * the UI shows "Not disclosed" rather than fabricating a number.
 */
export interface Tender {
  id: string;
  source_id: string;
  source_record_id: string;
  title: string;
  organization_name: string;
  department: string | null;
  organization_type: string | null;
  location: string | null;
  issue_date: string | null;
  publication_date: string | null;
  closing_date: string | null;
  award_date: string | null;
  estimated_value: number | null;
  currency: string | null;
  estimated_value_text: string | null;
  category: string | null;
  technologies: string[];
  scope_summary: string | null;
  tender_status: 'OPEN' | 'CLOSING_SOON' | 'CLOSED' | 'CANCELLED' | 'AWARDED' | 'UNKNOWN';
  source_url: string | null;
  company_id: number | null;
  target_company_id: number | null;
  signal_origin_organization: string | null;
  evidence_confidence: number;
  freshness_score: number;
  commercial_intent: string;
  data_provenance: string;
  first_seen_at: string | null;
  last_seen_at: string | null;
}

export interface TenderList {
  items: Tender[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface TenderListParams {
  page?: number;
  page_size?: number;
  status?: string;
  technology?: string;
  organization?: string;
  category?: string;
}

/** Paginated public tenders (GET /tenders). */
export async function fetchTenders(
  params: TenderListParams = {},
  signal?: AbortSignal,
): Promise<TenderList> {
  const { data } = await api.get<TenderList>('/tenders', { params, signal });
  return data;
}

/** A single tender (GET /tenders/{id}). */
export async function fetchTender(id: string, signal?: AbortSignal): Promise<Tender> {
  const { data } = await api.get<Tender>(`/tenders/${id}`, { signal });
  return data;
}

export interface TenderStatusDisplay {
  label: string;
  className: string;
}

const EMERALD = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
const BLUE = 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300';
const AMBER = 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300';
const SLATE = 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';

const STATUS_DISPLAY: Record<Tender['tender_status'], TenderStatusDisplay> = {
  OPEN: { label: 'Open', className: EMERALD },
  CLOSING_SOON: { label: 'Closing soon', className: AMBER },
  AWARDED: { label: 'Awarded', className: BLUE },
  CLOSED: { label: 'Closed', className: SLATE },
  CANCELLED: { label: 'Cancelled', className: SLATE },
  UNKNOWN: { label: 'Unknown', className: SLATE },
};

/** Display label + honest Tailwind badge classes for a tender status. */
export function tenderStatusDisplay(status: string): TenderStatusDisplay {
  return STATUS_DISPLAY[status as Tender['tender_status']] ?? { label: status, className: SLATE };
}

/**
 * Honest estimated-value label: a formatted currency amount when disclosed, the
 * provided free-text estimate as a fallback, or "Not disclosed" — never a
 * fabricated number.
 */
export function tenderValueDisplay(tender: Tender): string {
  if (tender.estimated_value !== null && tender.estimated_value !== undefined) {
    try {
      return new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency: tender.currency || 'USD',
        maximumFractionDigits: 0,
      }).format(tender.estimated_value);
    } catch {
      return `${tender.estimated_value.toLocaleString()}${tender.currency ? ` ${tender.currency}` : ''}`;
    }
  }
  if (tender.estimated_value_text) return tender.estimated_value_text;
  return 'Not disclosed';
}
