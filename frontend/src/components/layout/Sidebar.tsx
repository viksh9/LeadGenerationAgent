import { NavLink } from 'react-router-dom';
import { Radar, X } from 'lucide-react';
import { cn } from '@/utils/cn';
import { navItems } from '@/routes/navItems';

interface SidebarProps {
  /** Mobile drawer open state. */
  open: boolean;
  onClose: () => void;
}

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex-1 space-y-1 px-3 py-4" aria-label="Primary">
      {navItems.map(({ label, to, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          onClick={onNavigate}
          className={({ isActive }) => cn('nav-item', isActive && 'nav-item-active')}
        >
          <Icon className="h-5 w-5 shrink-0" />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-2 px-5 py-4">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-white">
        <Radar className="h-5 w-5" aria-hidden="true" />
      </span>
      <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">LeadGenerationAgent</span>
    </div>
  );
}

export function Sidebar({ open, onClose }: SidebarProps) {
  return (
    <>
      {/* Desktop / tablet: persistent sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 lg:flex">
        <Brand />
        <NavItems />
        <p className="px-5 py-4 text-xs text-slate-400 dark:text-slate-500">Phase 1 · v0.1.0</p>
      </aside>

      {/* Mobile: drawer */}
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-slate-900/40"
            onClick={onClose}
            aria-hidden="true"
          />
          <aside
            className="absolute inset-y-0 left-0 flex w-64 flex-col bg-white dark:bg-slate-900 shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
          >
            <div className="flex items-center justify-between">
              <Brand />
              <button
                type="button"
                className="btn-ghost mr-2"
                onClick={onClose}
                aria-label="Close navigation"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <NavItems onNavigate={onClose} />
          </aside>
        </div>
      )}
    </>
  );
}
