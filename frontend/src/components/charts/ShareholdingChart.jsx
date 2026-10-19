import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AXIS_COLOR, CATEGORICAL, GRID_COLOR, TEXT_MUTED } from "./chartTheme";

const HOLDER_SERIES = ["Promoters", "FIIs", "DIIs", "Government", "Public"];

function toChartRows(periods, series) {
  return periods.map((period, index) => {
    const row = { period };
    for (const key of Object.keys(series)) {
      row[key] = series[key][index];
    }
    return row;
  });
}

/**
 * Stacked holding-% bars plus a separate shareholder-count line.
 * Deliberately two charts, not one dual-axis chart: a % scale (0-100) and a
 * shareholder headcount scale are unrelated magnitudes, and dual y-axes make
 * a chart unreadable (which series does which axis?) - two single-axis
 * charts sharing the same x-axis read correctly instead.
 */
export default function ShareholdingChart({ periods, series, title }) {
  if (!periods?.length) {
    return <p className="analyser-empty">No shareholding data available for {title}.</p>;
  }

  const rows = toChartRows(periods, series);
  const holderSeries = HOLDER_SERIES.filter((key) => key in series);
  const shareholderCountKey = "No. of Shareholders";

  return (
    <div className="chart-card">
      <h4 className="chart-title">{title} shareholding pattern</h4>
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={rows} margin={{ top: 12, right: 12, left: 4, bottom: 4 }}>
          <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="period"
            tick={{ fill: TEXT_MUTED, fontSize: 11 }}
            stroke={AXIS_COLOR}
            angle={-35}
            textAnchor="end"
            height={55}
          />
          <YAxis
            tick={{ fill: TEXT_MUTED, fontSize: 11 }}
            stroke={AXIS_COLOR}
            width={44}
            unit="%"
          />
          <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155" }} />
          <Legend
            wrapperStyle={{ fontSize: 12, color: TEXT_MUTED }}
            payload={holderSeries.map((key, index) => ({
              value: key,
              type: "square",
              color: CATEGORICAL[index % CATEGORICAL.length],
            }))}
          />
          {holderSeries.map((key, index) => (
            <Bar key={key} dataKey={key} stackId="holding" fill={CATEGORICAL[index % CATEGORICAL.length]} />
          ))}
        </BarChart>
      </ResponsiveContainer>

      {shareholderCountKey in series && (
        <>
          <h5 className="chart-subtitle">Number of shareholders</h5>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={rows} margin={{ top: 12, right: 12, left: 4, bottom: 4 }}>
              <CartesianGrid stroke={GRID_COLOR} strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="period"
                tick={{ fill: TEXT_MUTED, fontSize: 11 }}
                stroke={AXIS_COLOR}
                angle={-35}
                textAnchor="end"
                height={55}
              />
              <YAxis tick={{ fill: TEXT_MUTED, fontSize: 11 }} stroke={AXIS_COLOR} width={64} />
              <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155" }} />
              <Line
                type="monotone"
                dataKey={shareholderCountKey}
                stroke={CATEGORICAL[0]}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </>
      )}
    </div>
  );
}
