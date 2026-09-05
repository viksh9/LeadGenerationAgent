import { useCallback, useState } from 'react';
import {
  DEFAULT_PREFERENCES,
  getPreferences,
  resetPreferences,
  savePreferences,
} from '@/services/preferences';
import type { Preferences } from '@/types/settings';

/** React state synced to the local preferences store. */
export function usePreferences() {
  const [prefs, setPrefs] = useState<Preferences>(getPreferences);

  const update = useCallback(<K extends keyof Preferences>(key: K, value: Preferences[K]) => {
    setPrefs((prev) => {
      const next = { ...prev, [key]: value };
      savePreferences(next);
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    resetPreferences();
    setPrefs({ ...DEFAULT_PREFERENCES });
  }, []);

  return { prefs, update, reset };
}
