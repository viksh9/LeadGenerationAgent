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

/**
 * Download the real-data Excel workbook for the given scope. Streams the .xlsx as
 * a blob and triggers a browser download. Returns the actual filename + row count
 * reported by the server (never fabricated).
 */
export async function downloadExcel(scope: ExportScope = 'all'): Promise<{ filename: string; rows: number }> {
  const res = await api.get('/export/excel', { params: { scope }, responseType: 'blob' });
  const headers = res.headers as Record<string, string | undefined>;
  const contentType =
    headers['content-type'] ??
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  const filename = headers['x-export-filename'] ?? `leadgenerationagent_${scope}_data.xlsx`;
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
