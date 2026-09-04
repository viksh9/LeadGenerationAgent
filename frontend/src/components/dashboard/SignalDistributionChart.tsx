import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Card, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/States';
import type { SignalDistributionDatum } from '@/types/dashboard';

export function SignalDistributionChart({ data }: { data: SignalDistributionDatum[] }) {
  const total = data.reduce((sum, d) => sum + d.count, 0);
  const summary = data
    .filter((d) => d.count > 0)
    .map((d) => `${d.label}: ${d.count}`)
    .join(', ');

  return (
    <Card>
      <CardTitle>Signal Distribution</CardTitle>
      {total === 0 ? (
        <EmptyState title="No signals detected" />
      ) : (
        <div
          className="mt-4 h-64"
          role="img"
          aria-label={`Signal distribution across the retrieved leads. ${summary}.`}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
              <CartesianGrid horizontal={false} stroke="#f1f5f9" />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 12, fill: '#64748b' }} />
              <YAxis
                type="category"
                dataKey="label"
                width={130}
                tick={{ fontSize: 12, fill: '#475569' }}
              />
              <Tooltip
                cursor={{ fill: '#f8fafc' }}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0' }}
              />
              <Bar dataKey="count" name="Leads" fill="#2563eb" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
