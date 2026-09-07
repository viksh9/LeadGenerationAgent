import { Card, CardTitle } from '@/components/ui/Card';
import { Table, Td, Th } from '@/components/ui/Table';
import type { IndustryStatistics } from '@/types/analytics';

/** Leads by industry + opportunity cross-analysis (§8 / §17). */
export function IndustryAnalysis({ industries }: { industries: IndustryStatistics[] }) {
  return (
    <Card padded={false}>
      <div className="px-5 pt-5">
        <CardTitle>Industry &amp; opportunity insight</CardTitle>
      </div>
      {industries.length === 0 ? (
        <p className="p-5 text-sm text-slate-400 dark:text-slate-500">Not enough data yet</p>
      ) : (
        <div className="mt-3">
          <Table>
            <thead>
              <tr>
                <Th>Industry</Th>
                <Th>Leads</Th>
                <Th>Hot</Th>
                <Th>Avg score</Th>
                <Th>High staffing</Th>
                <Th>Top opportunity</Th>
              </tr>
            </thead>
            <tbody>
              {industries.map((row) => (
                <tr key={row.industry}>
                  <Td>
                    <span className="font-medium text-slate-900 dark:text-slate-100">{row.industry}</span>
                  </Td>
                  <Td>
                    <span className="tabular-nums">{row.leads}</span>
                  </Td>
                  <Td>
                    <span className="tabular-nums">{row.hotLeads}</span>
                  </Td>
                  <Td>
                    <span className="tabular-nums">{row.averageScore}</span>
                  </Td>
                  <Td>
                    <span className="tabular-nums">{row.highStaffing}</span>
                  </Td>
                  <Td>
                    <span className="whitespace-nowrap text-slate-700 dark:text-slate-300">
                      {row.topOpportunityLabel ?? '—'}
                    </span>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        </div>
      )}
    </Card>
  );
}
