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
import type { ChartSpec } from '../types';
import { formatAxisValue } from '../utils/chartMessage';

interface ChartCardProps {
  spec: ChartSpec;
}

const PIE_COLORS = [
  '#6366f1',
  '#8b5cf6',
  '#a855f7',
  '#ec4899',
  '#f43f5e',
  '#f97316',
  '#eab308',
  '#22c55e',
];

function PieLegend({
  chartData,
}: {
  chartData: { name: string; value: number }[];
}) {
  const total = chartData.reduce((sum, item) => sum + item.value, 0);
  const columns = chartData.length > 4 ? 2 : 1;

  return (
    <ul
      className="grid gap-x-6 gap-y-2 border-t border-slate-200/80 pt-3 dark:border-slate-700"
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
    >
      {chartData.map((item, index) => {
        const pct = total > 0 ? ((item.value / total) * 100).toFixed(1) : '0.0';
        return (
          <li
            key={item.name}
            className="flex min-w-0 items-center gap-2 text-xs text-slate-700 dark:text-slate-200"
          >
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: PIE_COLORS[index % PIE_COLORS.length] }}
            />
            <span className="truncate">{item.name}</span>
            <span className="ml-auto shrink-0 tabular-nums font-medium text-slate-500 dark:text-slate-400">
              {pct}%
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function BarChartView({
  spec,
  chartData,
}: {
  spec: ChartSpec;
  chartData: { name: string; value: number }[];
}) {
  return (
    <BarChart
      data={chartData}
      margin={{ top: 8, right: 16, left: 8, bottom: 8 }}
    >
      <CartesianGrid
        strokeDasharray="3 3"
        className="stroke-slate-200 dark:stroke-slate-700"
      />
      <XAxis
        dataKey="name"
        tick={{ fontSize: 12 }}
        className="fill-slate-600 dark:fill-slate-400"
        interval={0}
        angle={chartData.length > 5 ? -25 : 0}
        textAnchor={chartData.length > 5 ? 'end' : 'middle'}
        height={chartData.length > 5 ? 60 : 30}
      />
      <YAxis
        tick={{ fontSize: 12 }}
        className="fill-slate-600 dark:fill-slate-400"
        tickFormatter={formatAxisValue}
      />
      <Tooltip
        formatter={(value) => {
          const num = typeof value === 'number' ? value : Number(value ?? 0);
          return [num.toLocaleString('zh-CN'), spec.y_label];
        }}
        contentStyle={{
          borderRadius: '0.75rem',
          border: '1px solid rgb(226 232 240)',
          fontSize: '12px',
        }}
      />
      <Bar
        dataKey="value"
        fill="#6366f1"
        radius={[6, 6, 0, 0]}
        maxBarSize={56}
      />
    </BarChart>
  );
}

function LineChartView({
  spec,
  chartData,
}: {
  spec: ChartSpec;
  chartData: { name: string; value: number }[];
}) {
  const tickAngle = chartData.length > 8 ? -35 : chartData.length > 5 ? -25 : 0;

  return (
    <LineChart
      data={chartData}
      margin={{ top: 12, right: 20, left: 8, bottom: chartData.length > 5 ? 20 : 8 }}
    >
      <CartesianGrid
        strokeDasharray="3 3"
        className="stroke-slate-200 dark:stroke-slate-700"
      />
      <XAxis
        dataKey="name"
        tick={{ fontSize: 11 }}
        className="fill-slate-600 dark:fill-slate-400"
        interval={chartData.length > 12 ? Math.floor(chartData.length / 8) : 0}
        angle={tickAngle}
        textAnchor={tickAngle ? 'end' : 'middle'}
        height={tickAngle ? 56 : 32}
      />
      <YAxis
        tick={{ fontSize: 12 }}
        className="fill-slate-600 dark:fill-slate-400"
        tickFormatter={formatAxisValue}
        width={48}
      />
      <Tooltip
        formatter={(value) => {
          const num = typeof value === 'number' ? value : Number(value ?? 0);
          return [num.toLocaleString('zh-CN'), spec.y_label];
        }}
        contentStyle={{
          borderRadius: '0.75rem',
          border: '1px solid rgb(226 232 240)',
          fontSize: '12px',
        }}
      />
      <Line
        type="monotone"
        dataKey="value"
        stroke="#6366f1"
        strokeWidth={2.5}
        dot={{ r: 4, fill: '#6366f1', strokeWidth: 0 }}
        activeDot={{ r: 6, fill: '#818cf8' }}
      />
    </LineChart>
  );
}

function PieChartView({
  chartData,
  yLabel,
}: {
  chartData: { name: string; value: number }[];
  yLabel: string;
}) {
  const total = chartData.reduce((sum, item) => sum + item.value, 0);

  return (
    <div className="flex flex-col gap-3">
      <div className="mx-auto aspect-square w-full max-w-[240px]">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              dataKey="value"
              nameKey="name"
              cx="50%"
              cy="50%"
              outerRadius="92%"
              paddingAngle={2}
              stroke="transparent"
              label={false}
              labelLine={false}
            >
              {chartData.map((entry, index) => (
                <Cell
                  key={entry.name}
                  fill={PIE_COLORS[index % PIE_COLORS.length]}
                />
              ))}
            </Pie>
            <Tooltip
              formatter={(value, _name, item) => {
                const num = typeof value === 'number' ? value : Number(value ?? 0);
                const pct = total > 0 ? ((num / total) * 100).toFixed(1) : '0';
                const label =
                  (item as { payload?: { name?: string } }).payload?.name ?? '';
                return [`${num.toLocaleString('zh-CN')} (${pct}%)`, label || yLabel];
              }}
              contentStyle={{
                borderRadius: '0.75rem',
                border: '1px solid rgb(226 232 240)',
                fontSize: '12px',
              }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <PieLegend chartData={chartData} />
    </div>
  );
}

export default function ChartCard({ spec }: ChartCardProps) {
  const chartData = spec.data.map((point) => ({
    name: point.label,
    value: point.value,
  }));

  const typeLabel =
    spec.type === 'pie' ? '扇形图' : spec.type === 'line' ? '折线图' : '柱状图';
  const isPie = spec.type === 'pie';
  const isLine = spec.type === 'line';

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-slate-200/80 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900/40">
      <div className="border-b border-slate-200/80 px-4 py-3 dark:border-slate-700">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-semibold leading-snug text-slate-800 dark:text-slate-100">
            {spec.title}
          </h4>
          <span className="shrink-0 rounded-full bg-brand-50 px-2 py-0.5 text-[10px] font-medium text-brand-600 dark:bg-brand-500/15 dark:text-brand-300">
            {typeLabel}
          </span>
        </div>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {spec.x_label} · {spec.y_label}
        </p>
      </div>

      {isPie ? (
        <div className="px-4 py-4">
          <PieChartView chartData={chartData} yLabel={spec.y_label} />
        </div>
      ) : (
        <div className="h-72 w-full px-2 py-3">
          <ResponsiveContainer width="100%" height="100%">
            {isLine ? (
              <LineChartView spec={spec} chartData={chartData} />
            ) : (
              <BarChartView spec={spec} chartData={chartData} />
            )}
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
