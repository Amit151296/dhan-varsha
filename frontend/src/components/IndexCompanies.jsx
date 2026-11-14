import { useEffect, useMemo, useRef, useState } from "react";
import { getIndexCompanies } from "../api/market";

const COLUMNS = [
  { key: "name", label: "Company" },
  { key: "sector", label: "Sector" },
  { key: "ltp", label: "Last price", numeric: true },
  { key: "day_change_pct", label: "Today", percent: true },
  { key: "market_cap_cr", label: "Market cap (Cr)", numeric: true },
  { key: "pe", label: "P/E", numeric: true },
  { key: "low_52w", label: "52W low", numeric: true },
  { key: "high_52w", label: "52W high", numeric: true },
  { key: "up_from_low_pct", label: "Up from 52W low", percent: true },
];

function pct(value) {
  if (value == null) return "-";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function tone(value) {
  if (value == null || value === 0) return "";
  return value > 0 ? "pnl-positive" : "pnl-negative";
}

// The companies inside one index. Loaded only when the index is clicked; the server saves each index's list for the day.
export default function IndexCompanies({ index, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [sort, setSort] = useState({ key: "market_cap_cr", direction: "desc" });
  const panel = useRef(null);

  useEffect(() => {
    let current = true;
    setData(null);
    setError("");
    getIndexCompanies(index.slug)
      .then((result) => current && setData(result))
      .catch((err) => current && setError(err?.response?.data?.detail || "Could not load the companies in this index."));
    panel.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    return () => {
      current = false; // a quick second click shouldn't be overwritten by the first reply
    };
  }, [index.slug]);

  const rows = useMemo(() => {
    if (!data) return [];
    const factor = sort.direction === "asc" ? 1 : -1;
    return [...data.rows].sort((a, b) => {
      const x = a[sort.key];
      const y = b[sort.key];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (typeof x === "string" ? x.localeCompare(y) : x - y) * factor;
    });
  }, [data, sort]);

  function toggleSort(column) {
    setSort((current) =>
      current.key === column.key
        ? { key: column.key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key: column.key, direction: column.key === "name" || column.key === "sector" ? "asc" : "desc" }
    );
  }

  return (
    <div ref={panel} className="index-companies">
      <h4>
        Companies in {index.name}
        {data ? ` (${data.rows.length})` : ""}{" "}
        <button type="button" className="link-button" onClick={onClose}>
          Close
        </button>
      </h4>
      {error && <p className="error-banner">{error}</p>}
      {!data && !error && <p className="analyser-empty">Loading companies...</p>}
      {data && (
        <>
          <p className="analysis-summary">
            Click a heading to sort. Largest companies first. Data fetched {new Date(data.fetched_at).toLocaleString()}
            ; saved for the day.
            {data.stale && " The data source could not be reached, so this is the last saved copy."}
          </p>
          <div className="metrics-table-wrapper">
            <table className="index-table">
              <thead>
                <tr>
                  {COLUMNS.map((column) => (
                    <th key={column.key} onClick={() => toggleSort(column)} style={{ cursor: "pointer" }}>
                      {column.label}
                      {sort.key === column.key ? (sort.direction === "asc" ? " ▲" : " ▼") : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.symbol || row.name}>
                    {COLUMNS.map((column) => {
                      const value = row[column.key];
                      const text = column.percent ? pct(value) : column.numeric ? value?.toLocaleString("en-IN") ?? "-" : value ?? "-";
                      return (
                        <td key={column.key} className={column.percent ? tone(value) : ""}>
                          {text}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
