import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

vi.mock('./api', () => ({ api: { get: vi.fn() } }));

import { api } from './api';
import { downloadExcel, fetchExportSummary } from './export';

const mockGet = vi.mocked(api.get);

describe('export service', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom lacks these — stub for the download side effect.
    (URL as unknown as { createObjectURL: () => string }).createObjectURL = vi.fn(() => 'blob:x');
    (URL as unknown as { revokeObjectURL: () => void }).revokeObjectURL = vi.fn();
  });

  afterEach(() => vi.restoreAllMocks());

  it('fetchExportSummary returns real counts', async () => {
    mockGet.mockResolvedValueOnce({ data: { counts: { Leads: 5 }, total_records: 5 } });
    const s = await fetchExportSummary();
    expect(s.total_records).toBe(5);
    expect(mockGet).toHaveBeenCalledWith('/export/summary');
  });

  it('downloadExcel reads the server filename + row count from headers', async () => {
    mockGet.mockResolvedValueOnce({
      data: new Blob(['x']),
      headers: {
        'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'x-export-filename': 'leadgenerationagent_all_data_2026-09-08.xlsx',
        'x-export-rows': '2519',
      },
    });
    const result = await downloadExcel('all');
    expect(result.filename).toBe('leadgenerationagent_all_data_2026-09-08.xlsx');
    expect(result.rows).toBe(2519);
    expect(mockGet).toHaveBeenCalledWith('/export/excel', { params: { scope: 'all' }, responseType: 'blob' });
  });

  it('downloadExcel falls back to a safe filename when the header is missing', async () => {
    mockGet.mockResolvedValueOnce({ data: new Blob(['x']), headers: {} });
    const result = await downloadExcel('leads');
    expect(result.filename).toBe('leadgenerationagent_leads_data.xlsx');
    expect(result.rows).toBe(0);
  });
});
