import { Card, CardTitle } from '@/components/ui/Card';
import { Table, Td, Th } from '@/components/ui/Table';
import type { SourceStatistics } from '@/types/analytics';

/** Leads by source (§14). Rendered only when sources exist. Counts only — no
 *  "best source" ranking is claimed without enough data. */
export function SourcePerformance({ sources }: { sources: SourceStatistics[] }) {
  if (sources.length === 0) return null;
  return (
    <Card padded={false}>
      <div className="px-5 pt-5">
        <CardTitle>Leads by source</CardTitle>
      </div>
      <div className="mt-3">
        <Table>
          <thead>
            <tr>
              <Th>Source</Th>
              <Th>Leads</Th>
              <Th>Hot</Th>
              <Th>Avg score</Th>
            </tr>
          </thead>
          <tbody>
            {sources.map((row) => (
              <tr key={row.source}>
                <Td>
                  <span className="font-medium text-slate-900 dark:text-slate-100">{row.source}</span>
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
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
    </Card>
  );
}
