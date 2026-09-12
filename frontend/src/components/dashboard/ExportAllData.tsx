import { useState } from 'react';
import { FileSpreadsheet, ChevronDown } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/contexts/ToastContext';
import { downloadExcel, downloadFullIntelligence, fetchExportSummary } from '@/services/export';
import type { ApiErrorShape } from '@/services/api';

type Format = 'lead-data' | 'full-intelligence';

const META: Record<Format, { title: string; label: string; note: string }> = {
  'lead-data': {
    title: 'Export Lead Data',
    label: 'Lead Data',
    note: 'the fixed 16-column sales report (one row per company-level lead)',
  },
  'full-intelligence': {
    title: 'Export Full Intelligence',
    label: 'Full Intelligence',
    note: 'the complete verified intelligence workbook (company identity, address, opportunity, POC, trust + per-field source)',
  },
};

/**
 * Dashboard export action. Offers two real-data workbooks — the fixed 16-column
 * "Lead Data" report and the richer "Full Intelligence" workbook — via a small menu,
 * then a confirmation dialog showing the actual record count. Failures show an honest
 * error (no fake fallback); nothing is ever described as demo/sample data.
 */
export function ExportAllData() {
  const toast = useToast();
  const [menuOpen, setMenuOpen] = useState(false);
  const [format, setFormat] = useState<Format | null>(null);
  const [exporting, setExporting] = useState(false);
  const [total, setTotal] = useState<number | null>(null);

  const choose = async (f: Format) => {
    setMenuOpen(false);
    setFormat(f);
    setTotal(null);
    try {
      const summary = await fetchExportSummary();
      setTotal(summary.total_records);
    } catch {
      setTotal(null); // dialog still works; count is best-effort
    }
  };

  const runExport = async () => {
    if (!format) return;
    setExporting(true);
    try {
      const { filename, rows } =
        format === 'full-intelligence' ? await downloadFullIntelligence() : await downloadExcel('all');
      toast.success(`${META[format].label} export is ready — ${filename} (${rows.toLocaleString()} rows).`);
      setFormat(null);
    } catch (e) {
      toast.error((e as ApiErrorShape)?.message ?? 'Unable to generate the Excel export.');
    } finally {
      setExporting(false);
    }
  };

  const description =
    format === null
      ? ''
      : total === null
        ? `This will export ${META[format].note} — all currently available real lead intelligence.`
        : `This will export ${META[format].note} for all ${total.toLocaleString()} currently available real leads.`;

  return (
    <>
      <div className="relative inline-block">
        <Button
          variant="primary"
          onClick={() => setMenuOpen((o) => !o)}
          disabled={exporting}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          aria-label="Export data to Excel"
          className="inline-flex items-center gap-2"
        >
          <FileSpreadsheet className="h-4 w-4" aria-hidden="true" />
          {exporting ? 'Preparing Excel…' : 'Export Data'}
          <ChevronDown className="h-4 w-4" aria-hidden="true" />
        </Button>
        {menuOpen && (
          <>
            <div className="fixed inset-0 z-10" aria-hidden="true" onClick={() => setMenuOpen(false)} />
            <div
              role="menu"
              className="absolute right-0 z-20 mt-1 w-56 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-800"
            >
              <button
                type="button"
                role="menuitem"
                className="block w-full px-4 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                onClick={() => choose('lead-data')}
              >
                Export Lead Data
                <span className="block text-xs text-slate-400 dark:text-slate-500">Fixed 16-column report</span>
              </button>
              <button
                type="button"
                role="menuitem"
                className="block w-full px-4 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-700"
                onClick={() => choose('full-intelligence')}
              >
                Export Full Intelligence
                <span className="block text-xs text-slate-400 dark:text-slate-500">Complete verified intelligence</span>
              </button>
            </div>
          </>
        )}
      </div>
      <ConfirmDialog
        open={format !== null}
        title={format ? META[format].title : ''}
        description={description}
        confirmLabel={exporting ? 'Preparing…' : 'Export Excel'}
        cancelLabel="Cancel"
        busy={exporting}
        onConfirm={runExport}
        onCancel={() => !exporting && setFormat(null)}
      />
    </>
  );
}
