import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { Card, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/States';
import { priorityColor } from '@/utils/format';
import type { PriorityDistributionDatum } from '@/types/dashboard';

export function PriorityDistributionChart({ data }: { data: PriorityDistributionDatum[] }) {
  const total = data.reduce((sum, d) => sum + d.count, 0);
  const summary = data.map((d) => `${d.priority}: ${d.count}`).join(', ');

  return (
    <Card>
      <CardTitle>Lead Priority</CardTitle>
      {total === 0 ? (
        <EmptyState title="No leads to summarize" />
      ) : (
        <div
          className="mt-4 h-64"
          role="img"
          aria-label={`Lead priority distribution. ${summary}.`}
        >
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="count"
                nameKey="priority"
                innerRadius={55}
                outerRadius={85}
                paddingAngle={2}
              >
                {data.map((d) => (
                  <Cell key={d.priority} fill={priorityColor[d.priority]} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0' }}
              />
              <Legend
                verticalAlign="bottom"
                height={24}
                formatter={(value) => <span className="text-xs text-slate-600">{value}</span>}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
