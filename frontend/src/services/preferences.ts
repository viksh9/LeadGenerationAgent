import { DEFAULT_PAGE_SIZE, PAGE_SIZE_OPTIONS } from '@/constants/leads';
import type { Preferences } from '@/types/settings';

/**
 * Local preferences store (localStorage). There is no backend settings/user
 * entity, so preferences are saved in this browser only. All access is guarded
 * so a disabled/absent localStorage falls back to defaults.
 */
const KEY = 'leadgen.preferences';

export const DEFAULT_PREFERENCES: Preferences = { leadsPageSize: DEFAULT_PAGE_SIZE };

export function getPreferences(): Preferences {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULT_PREFERENCES };
    const parsed = JSON.parse(raw) as Partial<Preferences>;
    const size = Number(parsed.leadsPageSize);
    return {
      leadsPageSize: PAGE_SIZE_OPTIONS.includes(size) ? size : DEFAULT_PREFERENCES.leadsPageSize,
    };
  } catch {
    return { ...DEFAULT_PREFERENCES };
  }
}

export function savePreferences(prefs: Preferences): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    // Storage may be unavailable (private mode) — preferences simply won't persist.
  }
}

export function resetPreferences(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}
