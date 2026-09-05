import { Card, CardTitle } from '@/components/ui/Card';
import { Table, Td, Th } from '@/components/ui/Table';
import type { TechnologyStatistics } from '@/types/analytics';

/** Technology demand + opportunity signal (§9 / §18). */
export function TechnologyDemand({ technologies }: { technologies: TechnologyStatistics[] }) {
  const max = technologies[0]?.leadCount ?? 1;
  return (
    <Card padded={false}>
      <div className="px-5 pt-5">
        <CardTitle>Technology demand</CardTitle>
      </div>
      {technologies.length === 0 ? (
        <p className="p-5 text-sm text-slate-400">Not enough data yet</p>
      ) : (
        <div className="mt-3">
          <Table>
            <thead>
              <tr>
                <Th>Technology</Th>
                <Th>Leads</Th>
                <Th>Hot</Th>
                <Th>Avg score</Th>
              </tr>
            </thead>
            <tbody>
              {technologies.map((row) => (
                <tr key={row.technology}>
                  <Td>
                    <span className="font-medium text-slate-900">{row.technology}</span>
                    <span
                      className="mt-1 block h-1.5 max-w-[10rem] overflow-hidden rounded-full bg-slate-100"
                      aria-hidden="true"
                    >
                      <span
                        className="block h-full rounded-full bg-brand-500"
                        style={{ width: `${Math.round((row.leadCount / max) * 100)}%` }}
                      />
                    </span>
                  </Td>
                  <Td>
                    <span className="tabular-nums">{row.leadCount}</span>
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
      )}
    </Card>
  );
}
