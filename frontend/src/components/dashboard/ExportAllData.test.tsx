import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '@/test/test-utils';
import { ExportAllData } from './ExportAllData';

vi.mock('@/services/export', () => ({
  fetchExportSummary: vi.fn(),
  downloadExcel: vi.fn(),
  downloadFullIntelligence: vi.fn(),
}));

import { downloadExcel, downloadFullIntelligence, fetchExportSummary } from '@/services/export';

const mockSummary = vi.mocked(fetchExportSummary);
const mockLeadData = vi.mocked(downloadExcel);
const mockFull = vi.mocked(downloadFullIntelligence);

describe('ExportAllData', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSummary.mockResolvedValue({ counts: { Leads: 326 }, total_records: 2519 });
    mockLeadData.mockResolvedValue({ filename: 'leadgenerationagent_lead_data_2026-09-08.xlsx', rows: 326 });
    mockFull.mockResolvedValue({ filename: 'leadgenerationagent_full_intelligence_2026-09-08.xlsx', rows: 326 });
  });

  it('shows an export button offering both formats', async () => {
    renderWithProviders(<ExportAllData />);
    await userEvent.click(screen.getByRole('button', { name: /export data to excel/i }));
    expect(screen.getByRole('menuitem', { name: /export lead data/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /export full intelligence/i })).toBeInTheDocument();
  });

  it('exports Lead Data (fixed report) on confirm', async () => {
    renderWithProviders(<ExportAllData />);
    await userEvent.click(screen.getByRole('button', { name: /export data to excel/i }));
    await userEvent.click(screen.getByRole('menuitem', { name: /export lead data/i }));
    await waitFor(() => expect(screen.getByText(/2,519/)).toBeInTheDocument());
    await userEvent.click(await screen.findByRole('button', { name: /export excel/i }));
    await waitFor(() => expect(mockLeadData).toHaveBeenCalledWith('all'));
    expect(mockFull).not.toHaveBeenCalled();
    expect(await screen.findByText(/Lead Data export is ready/i)).toBeInTheDocument();
  });

  it('exports Full Intelligence on confirm', async () => {
    renderWithProviders(<ExportAllData />);
    await userEvent.click(screen.getByRole('button', { name: /export data to excel/i }));
    await userEvent.click(screen.getByRole('menuitem', { name: /export full intelligence/i }));
    await userEvent.click(await screen.findByRole('button', { name: /export excel/i }));
    await waitFor(() => expect(mockFull).toHaveBeenCalled());
    expect(mockLeadData).not.toHaveBeenCalled();
    expect(await screen.findByText(/Full Intelligence export is ready/i)).toBeInTheDocument();
  });

  it('shows an honest error on failure (no fake fallback)', async () => {
    mockFull.mockRejectedValueOnce({ message: 'Unable to generate the Excel export.' });
    renderWithProviders(<ExportAllData />);
    await userEvent.click(screen.getByRole('button', { name: /export data to excel/i }));
    await userEvent.click(screen.getByRole('menuitem', { name: /export full intelligence/i }));
    await userEvent.click(await screen.findByRole('button', { name: /export excel/i }));
    expect(await screen.findByText(/Unable to generate the Excel export/i)).toBeInTheDocument();
  });
});
