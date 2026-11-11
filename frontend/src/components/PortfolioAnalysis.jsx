import { useEffect, useState } from "react";
import { getPortfolioAnalysis } from "../api/portfolio";

function rupees(value) {
  return value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function BreakdownTable({ title, labelHeader, rows }) {
  return (
    <section>
      <h4>{title}</h4>
      <div className="metrics-table-wrapper">
        <table className="metrics-table analysis-table">
          <thead>
            <tr>
              <th>{labelHeader}</th>
              <th>Companies</th>
              <th>Invested (Rs)</th>
              <th>Share of invested</th>
              <th>Current value (Rs)</th>
              <th>P&amp;L (Rs)</th>
              <th>Which companies</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <td>{row.label}</td>
                <td>{row.company_count}</td>
                <td>{rupees(row.invested)}</td>
                <td className="share-cell">
                  <span className="share-bar" style={{ width: `${Math.max(row.share_of_invested, 1) * 0.8}px` }} />
                  {row.share_of_invested}%
                </td>
                <td>{rupees(row.current_value)}</td>
                <td className={row.pnl < 0 ? "pnl-negative" : "pnl-positive"}>{rupees(row.pnl)}</td>
                <td className="analysis-companies">{row.companies.join(", ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// `refreshKey` changes whenever the holdings do, so the breakdown never goes stale.
export default function PortfolioAnalysis({ refreshKey }) {
  const [analysis, setAnalysis] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError("");
    getPortfolioAnalysis()
      .then((result) => {
        if (!cancelled) setAnalysis(result);
      })
      .catch(() => {
        if (!cancelled) setError("Could not build the portfolio analysis right now.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (error) return <p className="error-banner">{error}</p>;
  if (!analysis) return isLoading ? <p>Analysing your portfolio (looking up sectors the first time can take a few seconds)...</p> : null;
  if (analysis.company_count === 0) return null;

  return (
    <div className="analysis-section">
      <h3>Portfolio analysis</h3>
      <p className="analysis-summary">
        {analysis.company_count} {analysis.company_count === 1 ? "company" : "companies"} - Rs{" "}
        {rupees(analysis.total_invested)} invested{isLoading ? " (updating...)" : ""}
      </p>
      <BreakdownTable title="By broker" labelHeader="Broker" rows={analysis.by_broker} />
      <BreakdownTable title="By sector" labelHeader="Sector" rows={analysis.by_sector} />
    </div>
  );
}
