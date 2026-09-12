import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '@/test/test-utils';
import { ExportAllData } from './ExportAllData';

vi.mock('@/services/export', () => ({
  fetchExportSummary: vi.fn(),
  downloadExcel: vi.fn(),
}));

import { downloadExcel, fetchExportSummary } from '@/services/export';

const mockSummary = vi.mocked(fetchExportSummary);
const mockDownload = vi.mocked(downloadExcel);

describe('ExportAllData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSummary.mockResolvedValue({ counts: { Leads: 326 }, total_records: 2519 });
    mockDownload.mockResolvedValue({ filename: 'leadgenerationagent_all_data_2026-09-08.xlsx', rows: 2519 });
  });

  it('shows a prominent Export All Data button', () => {
    renderWithProviders(<ExportAllData />);
    expect(screen.getByRole('button', { name: /export all data to excel/i })).toBeInTheDocument();
  });

  it('opens a confirmation dialog with the real record count', async () => {
    renderWithProviders(<ExportAllData />);
    await userEvent.click(screen.getByRole('button', { name: /export all data to excel/i }));
    expect(await screen.findByText(/Export All Lead Data/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/2,519 leads/i)).toBeInTheDocument());
    expect(screen.getByText(/single Excel worksheet/i)).toBeInTheDocument();
    // Never described as demo/sample.
    expect(screen.queryByText(/demo|sample|dummy/i)).not.toBeInTheDocument();
  });

  it('downloads the workbook on confirm and reports the real filename + count', async () => {
    renderWithProviders(<ExportAllData />);
    await userEvent.click(screen.getByRole('button', { name: /export all data to excel/i }));
    const confirm = await screen.findByRole('button', { name: /export excel/i });
    await userEvent.click(confirm);
    await waitFor(() => expect(mockDownload).toHaveBeenCalledWith('all'));
    expect(await screen.findByText(/Excel export is ready/i)).toBeInTheDocument();
    expect(screen.getByText(/leadgenerationagent_all_data_2026-09-08\.xlsx/)).toBeInTheDocument();
  });

  it('shows an honest error on failure (no fake fallback)', async () => {
    mockDownload.mockRejectedValueOnce({ message: 'Unable to generate the Excel export.' });
    renderWithProviders(<ExportAllData />);
    await userEvent.click(screen.getByRole('button', { name: /export all data to excel/i }));
    await userEvent.click(await screen.findByRole('button', { name: /export excel/i }));
    expect(await screen.findByText(/Unable to generate the Excel export/i)).toBeInTheDocument();
  });
});
