import { api } from './api';

/**
 * A verified business signal from the backend (GET /signals). Every field maps
 * to a real collected record — nothing is fabricated. Nullable fields stay
 * nullable so the UI can render honest "not available" states.
 */
export interface Signal {
  id: string;
  company_id: number | null;
  company_name: string | null;
  signal_type: string;
  signal_title: string | null;
  signal_description: string | null;
  signal_url: string | null;
  published_at: string | null;
  technologies: string[];
  location: string | null;
  signal_strength: 'STRONG' | 'MEDIUM' | 'WEAK';
  source_id: string;
  source_count: number;
  evidence_confidence: number;
  commercial_intent: 'VERY_HIGH' | 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN';
  data_provenance: string;
}

export interface SignalList {
  items: Signal[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface SignalListParams {
  page?: number;
  page_size?: number;
  signal_type?: string;
  company?: string;
  technology?: string;
  source?: string;
}

/** Paginated verified business signals (GET /signals). */
export async function fetchSignals(
  params: SignalListParams = {},
  signal?: AbortSignal,
): Promise<SignalList> {
  const { data } = await api.get<SignalList>('/signals', { params, signal });
  return data;
}

/** A single verified business signal (GET /signals/{id}). */
export async function fetchSignal(id: string, signal?: AbortSignal): Promise<Signal> {
  const { data } = await api.get<Signal>(`/signals/${id}`, { signal });
  return data;
}

export interface BadgeDisplay {
  label: string;
  className: string;
}

const EMERALD = 'bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300';
const BLUE = 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300';
const AMBER = 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300';
const SLATE = 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300';

const STRENGTH_DISPLAY: Record<Signal['signal_strength'], BadgeDisplay> = {
  STRONG: { label: 'Strong', className: EMERALD },
  MEDIUM: { label: 'Medium', className: AMBER },
  WEAK: { label: 'Weak', className: SLATE },
};

/** Display label + honest Tailwind badge classes for a signal strength. */
export function signalStrengthDisplay(strength: string): BadgeDisplay {
  return STRENGTH_DISPLAY[strength as Signal['signal_strength']] ?? { label: strength, className: SLATE };
}

const INTENT_DISPLAY: Record<Signal['commercial_intent'], BadgeDisplay> = {
  VERY_HIGH: { label: 'Very high', className: EMERALD },
  HIGH: { label: 'High', className: BLUE },
  MEDIUM: { label: 'Medium', className: AMBER },
  LOW: { label: 'Low', className: SLATE },
  UNKNOWN: { label: 'Unknown', className: SLATE },
};

/** Display label + honest Tailwind badge classes for a commercial-intent band. */
export function commercialIntentDisplay(intent: string): BadgeDisplay {
  return INTENT_DISPLAY[intent as Signal['commercial_intent']] ?? { label: intent, className: SLATE };
}
