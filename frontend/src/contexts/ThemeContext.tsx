/* eslint-disable react-refresh/only-export-components -- context module exports a provider + helpers by design */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { getPreferences, savePreferences } from '@/services/preferences';
import type { ThemePreference } from '@/types/settings';

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-color-scheme: dark)').matches;
}

/** Apply (or clear) the `dark` class on <html> based on the preference. */
export function applyTheme(theme: ThemePreference): void {
  if (typeof document === 'undefined') return;
  const dark = theme === 'dark' || (theme === 'system' && systemPrefersDark());
  document.documentElement.classList.toggle('dark', dark);
}

interface ThemeContextValue {
  theme: ThemePreference;
  resolved: 'light' | 'dark';
  setTheme: (theme: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemePreference>(() => getPreferences().theme);

  useEffect(() => {
    applyTheme(theme);
    if (theme !== 'system') return;
    const mq = window.matchMedia?.('(prefers-color-scheme: dark)');
    if (!mq) return;
    const handler = () => applyTheme('system');
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [theme]);

  const setTheme = useCallback((next: ThemePreference) => {
    setThemeState(next);
    savePreferences({ ...getPreferences(), theme: next });
    applyTheme(next);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ theme, resolved: theme === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : theme, setTheme }),
    [theme, setTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useThemeContext(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useThemeContext must be used within a ThemeProvider');
  return ctx;
}
