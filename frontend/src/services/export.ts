import { api } from './api';

export interface ExportSummary {
  counts: Record<string, number>;
  total_records: number;
}

export type ExportScope = 'all' | 'leads' | 'companies' | 'jobs' | 'opportunities' | 'contacts';

/** Actual counts of what an export would contain (real DB data). */
export async function fetchExportSummary(): Promise<ExportSummary> {
  const { data } = await api.get<ExportSummary>('/export/summary');
  return data;
}

const _XLSX_MEDIA = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

/** Stream an .xlsx blob response to a browser download. Returns the actual filename +
 *  row count reported by the server (never fabricated). */
function _saveBlob(res: { data: BlobPart; headers: unknown }, fallbackName: string) {
  const headers = res.headers as Record<string, string | undefined>;
  const contentType = headers['content-type'] ?? _XLSX_MEDIA;
  const filename = headers['x-export-filename'] ?? fallbackName;
  const rows = Number(headers['x-export-rows'] ?? 0);
  const blob = new Blob([res.data], { type: contentType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return { filename, rows };
}

/**
 * Download the fixed 16-column "Lead Data" Excel workbook for the given scope.
 */
export async function downloadExcel(scope: ExportScope = 'all'): Promise<{ filename: string; rows: number }> {
  const res = await api.get('/export/excel', { params: { scope }, responseType: 'blob' });
  return _saveBlob(res, `leadgenerationagent_${scope}_data.xlsx`);
}

/**
 * Download the "Full Intelligence" Excel workbook — the complete real verified sales
 * intelligence (separate from the fixed 16-column Lead Data export).
 */
export async function downloadFullIntelligence(): Promise<{ filename: string; rows: number }> {
  const res = await api.get('/export/full-intelligence', { responseType: 'blob' });
  return _saveBlob(res, 'leadgenerationagent_full_intelligence.xlsx');
}
