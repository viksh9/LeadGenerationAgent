import { Moon, Sun } from 'lucide-react';
import { useThemeContext } from '@/contexts/ThemeContext';

/** Header toggle: flips between light and dark (system default lives in Settings). */
export function ThemeToggle() {
  const { resolved, setTheme } = useThemeContext();
  const next = resolved === 'dark' ? 'light' : 'dark';
  return (
    <button
      type="button"
      className="btn-ghost"
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
    >
      {resolved === 'dark' ? (
        <Sun className="h-5 w-5" aria-hidden="true" />
      ) : (
        <Moon className="h-5 w-5" aria-hidden="true" />
      )}
    </button>
  );
}
