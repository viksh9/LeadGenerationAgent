import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { DistributionDatum, LeadTrendPoint } from '@/types/analytics';

const AXIS_TICK = { fontSize: 11, fill: '#64748b' };
const TOOLTIP_STYLE = { fontSize: 12, borderRadius: 8, border: '1px solid rgba(100,116,139,0.35)' };
const PALETTE = ['#2563eb', '#0891b2', '#7c3aed', '#d97706', '#059669', '#db2777', '#64748b', '#94a3b8', '#0ea5e9'];

function NotEnough() {
  return <p className="py-8 text-center text-sm text-slate-400 dark:text-slate-500">Not enough data yet</p>;
}

/** Donut chart for a small distribution (e.g. priority), with a colour map. */
export function DonutDistribution({
  data,
  colorFor,
  ariaLabel,
}: {
  data: DistributionDatum[];
  colorFor?: (key: string) => string;
  ariaLabel: string;
}) {
  if (data.length === 0) return <NotEnough />;
  const summary = data.map((d) => `${d.label}: ${d.count} (${d.percentage}%)`).join(', ');
  return (
    <div className="h-56" role="img" aria-label={`${ariaLabel}. ${summary}.`}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey="count" nameKey="label" innerRadius={48} outerRadius={78} paddingAngle={2}>
            {data.map((d, i) => (
              <Cell key={d.key} fill={colorFor ? colorFor(d.key) : PALETTE[i % PALETTE.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={TOOLTIP_STYLE} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Horizontal bar chart for a labelled distribution. */
export function BarDistribution({ data, ariaLabel }: { data: DistributionDatum[]; ariaLabel: string }) {
  if (data.length === 0) return <NotEnough />;
  const summary = data.map((d) => `${d.label}: ${d.count}`).join(', ');
  const height = Math.max(160, data.length * 34);
  return (
    <div style={{ height }} role="img" aria-label={`${ariaLabel}. ${summary}.`}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="rgba(100,116,139,0.18)" />
          <XAxis type="number" allowDecimals={false} tick={AXIS_TICK} />
          <YAxis type="category" dataKey="label" width={140} tick={AXIS_TICK} />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Bar dataKey="count" radius={[0, 4, 4, 0]}>
            {data.map((d, i) => (
              <Cell key={d.key} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Line chart for a time trend (count or averageScore). */
export function LineTrend({
  data,
  dataKey,
  ariaLabel,
}: {
  data: LeadTrendPoint[];
  dataKey: 'count' | 'averageScore';
  ariaLabel: string;
}) {
  if (data.length < 2) return <NotEnough />;
  const summary = data.map((d) => `${d.label}: ${d[dataKey]}`).join(', ');
  return (
    <div className="h-56" role="img" aria-label={`${ariaLabel}. ${summary}.`}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ left: -12, right: 12, top: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(100,116,139,0.18)" />
          <XAxis dataKey="label" tick={AXIS_TICK} />
          <YAxis allowDecimals={false} tick={AXIS_TICK} />
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Line type="monotone" dataKey={dataKey} stroke="#2563eb" strokeWidth={2} dot={{ r: 2 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
