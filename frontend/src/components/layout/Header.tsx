import { useLocation } from 'react-router-dom';
import { Bell, Menu } from 'lucide-react';
import { navItems } from '@/routes/navItems';

function usePageTitle(): string {
  const { pathname } = useLocation();
  const match = navItems.find((item) => pathname.startsWith(item.to));
  return match?.label ?? 'LeadGenerationAgent';
}

export function Header({ onMenuClick }: { onMenuClick: () => void }) {
  const title = usePageTitle();
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur sm:px-6">
      <button
        type="button"
        className="btn-ghost lg:hidden"
        onClick={onMenuClick}
        aria-label="Open navigation"
      >
        <Menu className="h-5 w-5" />
      </button>

      <h1 className="text-base font-semibold text-slate-900">{title}</h1>

      <div className="ml-auto flex items-center gap-2">
        <button type="button" className="btn-ghost relative" aria-label="Notifications">
          <Bell className="h-5 w-5" />
        </button>
        {/* User/profile placeholder — authentication not implemented yet. */}
        <div className="flex items-center gap-2 rounded-full border border-slate-200 py-1 pl-1 pr-3">
          <span
            className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-200 text-xs font-semibold text-slate-600"
            aria-hidden="true"
          >
            BD
          </span>
          <span className="hidden text-sm text-slate-600 sm:inline">BD Team</span>
        </div>
      </div>
    </header>
  );
}
