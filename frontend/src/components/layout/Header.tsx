import { useLocation } from 'react-router-dom';
import { Menu } from 'lucide-react';
import { navItems } from '@/routes/navItems';
import { ThemeToggle } from '@/components/layout/ThemeToggle';
import { AlertCenter } from '@/components/alerts/AlertCenter';

function usePageTitle(): string {
  const { pathname } = useLocation();
  const match = navItems.find((item) => pathname.startsWith(item.to));
  return match?.label ?? 'LeadGenerationAgent';
}

export function Header({ onMenuClick }: { onMenuClick: () => void }) {
  const title = usePageTitle();
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-slate-200 dark:border-slate-800 bg-white/90 dark:bg-slate-900/80 px-4 backdrop-blur sm:px-6">
      <button
        type="button"
        className="btn-ghost lg:hidden"
        onClick={onMenuClick}
        aria-label="Open navigation"
      >
        <Menu className="h-5 w-5" />
      </button>

      <h1 className="text-base font-semibold text-slate-900 dark:text-slate-100">{title}</h1>

      <div className="ml-auto flex items-center gap-2">
        <ThemeToggle />
        <AlertCenter />
        {/* User/profile placeholder — authentication not implemented yet. */}
        <div className="flex items-center gap-2 rounded-full border border-slate-200 dark:border-slate-800 py-1 pl-1 pr-3">
          <span
            className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-200 dark:bg-slate-700 text-xs font-semibold text-slate-600 dark:text-slate-300"
            aria-hidden="true"
          >
            BD
          </span>
          <span className="hidden text-sm text-slate-600 dark:text-slate-300 sm:inline">BD Team</span>
        </div>
      </div>
    </header>
  );
}
