import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AXIS_COLOR, GRID_COLOR, METRIC_BAR_COLOR, TEXT_MUTED, growthColor } from "./chartTheme";

const SPACER_PREFIX = "__sep__";

function ChangeLabel({ x, y, width, value }) {
  if (value == null) return null;
  const text = `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
  return (
    <text
      x={x + width / 2}
      y={y - 6}
      textAnchor="middle"
      fontSize={11}
      fill={growthColor(value)}
    >
      {text}
    </text>
  );
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  if (point.value == null) return null; // spacer category - nothing to show
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-title">{label}</div>
      <div>Value: {point.value?.toLocaleString() ?? "—"}</div>
      {point.change_pct != null && (
        <div style={{ color: growthColor(point.change_pct) }}>
          Change: {point.change_pct > 0 ? "+" : ""}
          {point.change_pct}%
        </div>
      )}
    </div>
  );
}

function formatAxisTick(value) {
  return String(value).startsWith(SPACER_PREFIX) ? "" : value;
}

/**
 * Bar chart for a single metric's values over time, with a % change label per bar.
 * With `groupByQuarter`, periods are already arranged by the backend into
 * same-quarter groups (all the Decembers, then all the Junes, ...) - this
 * draws a separator between groups using the `group_start` flag already on
 * the data, matching the original tool's quarter-grouped layout.
 *
 * Recharts has no way to put a ReferenceLine *between* two category bars -
 * `x` always centers on one category's band. So a zero-value spacer category
 * is inserted at each group boundary and the line is drawn through that thin
 * gap instead, landing exactly between the real bars on either side.
 */
export default function GrowthBarChart({ data, title, unit = "", groupByQuarter = false }) {
  if (!data?.length) {
    return <p className="analyser-empty">No data available for {title}.</p>;
  }

  const chartData = [];
  const separators = [];
  data.forEach((entry, index) => {
    if (groupByQuarter && index > 0 && entry.group_start) {
      const spacerPeriod = `${SPACER_PREFIX}${index}`;
      chartData.push({ period: spacerPeriod, value: null, change_pct: null });
      separators.push(spacerPeriod);
    }
    chartData.push(entry);
  });

  return (
    <div className="chart-card">
      <h4 className="chart-title">
        {title}
        {unit && <span className="chart-unit"> ({unit})</span>}
      </h4>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={chartData} margin={{ top: 24, right: 12, left: 4, bottom: 4 }} barCategoryGap="20%">
          <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="period"
            tickFormatter={formatAxisTick}
            tick={{ fill: TEXT_MUTED, fontSize: 11 }}
            stroke={AXIS_COLOR}
            angle={-35}
            textAnchor="end"
            height={55}
            interval={0}
          />
          <YAxis tick={{ fill: TEXT_MUTED, fontSize: 11 }} stroke={AXIS_COLOR} width={56} />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
          {separators.map((period) => (
            <ReferenceLine key={period} x={period} stroke={AXIS_COLOR} strokeDasharray="4 4" />
          ))}
          <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={36}>
            {chartData.map((entry) => (
              <Cell
                key={entry.period}
                fill={entry.period.startsWith(SPACER_PREFIX) ? "transparent" : METRIC_BAR_COLOR}
              />
            ))}
            <LabelList dataKey="change_pct" content={ChangeLabel} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
