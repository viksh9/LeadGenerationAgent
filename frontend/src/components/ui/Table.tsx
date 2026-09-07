import type { ReactNode } from 'react';

/** A responsive table wrapper — horizontally scrollable on small screens. */
export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">{children}</table>
    </div>
  );
}

export function Th({ children }: { children: ReactNode }) {
  return (
    <th
      scope="col"
      className="border-b border-slate-200 dark:border-slate-800 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400"
    >
      {children}
    </th>
  );
}

export function Td({ children }: { children: ReactNode }) {
  return <td className="border-b border-slate-100 dark:border-slate-800 px-4 py-3 text-slate-700 dark:text-slate-300">{children}</td>;
}
