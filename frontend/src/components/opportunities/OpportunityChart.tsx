import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Card, CardTitle } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/States';
import type { OpportunityTypeDatum } from '@/types/opportunity';

// Restrained categorical palette aligned with the app's slate/brand tones.
const BAR_COLORS = ['#2563eb', '#0891b2', '#7c3aed', '#d97706', '#059669', '#db2777', '#64748b', '#94a3b8'];

/** Opportunity-type distribution (§25). Responsive bar chart. */
export function OpportunityChart({ data }: { data: OpportunityTypeDatum[] }) {
  const total = data.reduce((sum, d) => sum + d.count, 0);
  const summary = data.map((d) => `${d.label}: ${d.count}`).join(', ');

  return (
    <Card>
      <CardTitle>Opportunity type distribution</CardTitle>
      {total === 0 ? (
        <EmptyState title="No opportunities to summarize" />
      ) : (
        <div className="mt-4 h-72" role="img" aria-label={`Opportunity type distribution. ${summary}.`}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 4, right: 8, bottom: 60, left: -12 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
              <XAxis
                dataKey="label"
                angle={-35}
                textAnchor="end"
                interval={0}
                tick={{ fontSize: 11, fill: '#64748b' }}
                height={70}
              />
              <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#64748b' }} />
              <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0' }} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {data.map((d, i) => (
                  <Cell key={d.type} fill={BAR_COLORS[i % BAR_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}
