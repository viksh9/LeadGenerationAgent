import { afterEach, describe, expect, it } from 'vitest';
import { DEFAULT_PREFERENCES, getPreferences, resetPreferences, savePreferences } from './preferences';

afterEach(() => localStorage.clear());

describe('preferences store', () => {
  it('returns defaults when nothing is stored', () => {
    expect(getPreferences()).toEqual(DEFAULT_PREFERENCES);
  });

  it('round-trips a saved preference', () => {
    savePreferences({ leadsPageSize: 50, theme: 'system' });
    expect(getPreferences().leadsPageSize).toBe(50);
  });

  it('falls back to the default for an invalid stored value', () => {
    localStorage.setItem('leadgen.preferences', JSON.stringify({ leadsPageSize: 999 }));
    expect(getPreferences().leadsPageSize).toBe(DEFAULT_PREFERENCES.leadsPageSize);
  });

  it('resets to defaults', () => {
    savePreferences({ leadsPageSize: 100, theme: 'system' });
    resetPreferences();
    expect(getPreferences()).toEqual(DEFAULT_PREFERENCES);
  });
});
