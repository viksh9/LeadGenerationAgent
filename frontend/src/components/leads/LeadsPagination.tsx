import { ChevronLeft, ChevronRight } from 'lucide-react';
import { PAGE_SIZE_OPTIONS } from '@/constants/leads';

interface LeadsPaginationProps {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
}

export function LeadsPagination({
  page,
  pageSize,
  total,
  totalPages,
  onPage,
  onPageSize,
}: LeadsPaginationProps) {
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <div className="flex flex-col items-center justify-between gap-3 border-t border-slate-200 dark:border-slate-800 px-4 py-3 sm:flex-row">
      <p className="text-sm text-slate-500 dark:text-slate-400">
        Showing <span className="font-medium text-slate-700 dark:text-slate-300">{from}</span>–
        <span className="font-medium text-slate-700 dark:text-slate-300">{to}</span> of{' '}
        <span className="font-medium text-slate-700 dark:text-slate-300">{total.toLocaleString()}</span>
      </p>

      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
          <span className="hidden sm:inline">Per page</span>
          <select
            className="select w-auto py-1"
            value={pageSize}
            onChange={(e) => onPageSize(Number(e.target.value))}
            aria-label="Rows per page"
          >
            {PAGE_SIZE_OPTIONS.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center gap-1">
          <button
            type="button"
            className="btn-secondary px-2 py-1"
            onClick={() => onPage(page - 1)}
            disabled={page <= 1}
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="px-2 text-sm text-slate-600 dark:text-slate-300" aria-live="polite">
            Page {page} of {Math.max(totalPages, 1)}
          </span>
          <button
            type="button"
            className="btn-secondary px-2 py-1"
            onClick={() => onPage(page + 1)}
            disabled={page >= totalPages}
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
