import { useEffect, useMemo, useState } from "react";
import { downloadIndexPerformance, getIndexPerformance } from "../api/market";
import IndexCompanies from "./IndexCompanies";

const COLUMNS = [
  { key: "name", label: "Index" },
  { key: "ltp", label: "Last price", numeric: true },
  { key: "day_change_pct", label: "Today", percent: true },
  { key: "return_1w", label: "1 week", percent: true },
  { key: "return_1m", label: "1 month", percent: true },
  { key: "return_3m", label: "3 months", percent: true },
  { key: "return_6m", label: "6 months", percent: true },
  { key: "return_1y", label: "1 year", percent: true },
  { key: "return_3y", label: "3 years", percent: true },
  { key: "return_5y", label: "5 years", percent: true },
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

// NSE index performance for everyone (not per user). The server fetches it once a day and caches it until midnight IST.
// Sorting and filtering are left to Excel: "Download Excel" gives the same table with filter arrows on the headings.
export default function IndexPerformance() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [sort, setSort] = useState({ key: "name", direction: "asc" });
  const [openIndex, setOpenIndex] = useState(null);

  useEffect(() => {
    getIndexPerformance()
      .then(setData)
      .catch((err) => setError(err?.response?.data?.detail || "Could not load index performance."));
  }, []);

  const rows = useMemo(() => {
    if (!data) return [];
    const factor = sort.direction === "asc" ? 1 : -1;
    return [...data.rows].sort((a, b) => {
      const x = a[sort.key];
      const y = b[sort.key];
      if (x == null && y == null) return 0;
      if (x == null) return 1; // blanks always last
      if (y == null) return -1;
      return (typeof x === "string" ? x.localeCompare(y) : x - y) * factor;
    });
  }, [data, sort]);

  // First click on a number column puts the highest first; clicking again reverses it.
  function toggleSort(column) {
    setSort((current) =>
      current.key === column.key
        ? { key: column.key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key: column.key, direction: column.key === "name" ? "asc" : "desc" }
    );
  }

  async function handleDownload() {
    try {
      await downloadIndexPerformance();
    } catch {
      setError("Could not download the Excel file.");
    }
  }

  return (
    <section className="index-performance">
      <h3>NSE index performance</h3>
      {error && <p className="error-banner">{error}</p>}
      {!data && !error && <p className="analyser-empty">Loading indices...</p>}
      {data && (
        <>
          <p className="analysis-summary">
            Click a heading to sort, or an index name to see its companies. Data fetched {new Date(data.fetched_at).toLocaleString()}; it is the same for everyone and refreshes once a
            day at midnight (IST).
            {data.stale && " The data source could not be reached, so this is the last saved copy."}{" "}
            <button type="button" onClick={handleDownload}>
              Download Excel
            </button>
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
                  <tr key={row.name}>
                    {COLUMNS.map((column) => {
                      const value = row[column.key];
                      const text = column.percent ? pct(value) : column.numeric ? value?.toLocaleString("en-IN") ?? "-" : value;
                      return (
                        <td key={column.key} className={column.percent ? tone(value) : ""}>
                          {column.key === "name" && row.slug ? (
                            <button type="button" className="link-button" onClick={() => setOpenIndex(row)}>
                              {text}
                            </button>
                          ) : (
                            text
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {openIndex && <IndexCompanies index={openIndex} onClose={() => setOpenIndex(null)} />}
        </>
      )}
    </section>
  );
}
