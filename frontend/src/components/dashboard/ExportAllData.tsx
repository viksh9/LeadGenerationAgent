import { useState } from 'react';
import { FileSpreadsheet } from 'lucide-react';

import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/contexts/ToastContext';
import { downloadExcel, fetchExportSummary } from '@/services/export';
import type { ApiErrorShape } from '@/services/api';

/**
 * Prominent "Export All Data" action for the Dashboard. Opens a confirmation
 * dialog (showing the actual record count), then generates + downloads the real
 * .xlsx workbook. Duplicate clicks are prevented while exporting; failures show an
 * honest error (no fake fallback). Nothing is described as demo/sample data.
 */
export function ExportAllData() {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [total, setTotal] = useState<number | null>(null);

  const openDialog = async () => {
    setOpen(true);
    setTotal(null);
    try {
      const summary = await fetchExportSummary();
      setTotal(summary.total_records);
    } catch {
      setTotal(null); // dialog still works; count is best-effort
    }
  };

  const runExport = async () => {
    setExporting(true);
    try {
      const { filename, rows } = await downloadExcel('all');
      toast.success(`Excel export is ready — ${filename} (${rows.toLocaleString()} rows).`);
      setOpen(false);
    } catch (e) {
      toast.error((e as ApiErrorShape)?.message ?? 'Unable to generate the Excel export.');
    } finally {
      setExporting(false);
    }
  };

  const description =
    total === null
      ? 'This will export all currently available real data from the application database to an Excel (.xlsx) workbook.'
      : `This will export all currently available real data (${total.toLocaleString()} records) from the application database to an Excel (.xlsx) workbook.`;

  return (
    <>
      <Button
        variant="primary"
        onClick={openDialog}
        disabled={exporting}
        aria-label="Export all data to Excel"
        className="inline-flex items-center gap-2"
      >
        <FileSpreadsheet className="h-4 w-4" aria-hidden="true" />
        {exporting ? 'Preparing Excel…' : 'Export All Data'}
      </Button>
      <ConfirmDialog
        open={open}
        title="Export All Real Data"
        description={description}
        confirmLabel={exporting ? 'Preparing…' : 'Export Excel'}
        cancelLabel="Cancel"
        busy={exporting}
        onConfirm={runExport}
        onCancel={() => !exporting && setOpen(false)}
      />
    </>
  );
}
