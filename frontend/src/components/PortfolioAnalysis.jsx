import { useEffect, useState } from "react";
import { getPortfolioAnalysis } from "../api/portfolio";

function rupees(value) {
  return value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function pnlPercentText(pnl, invested) {
  if (!invested) return "-";
  const pct = (pnl / invested) * 100;
  return `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

function BreakdownTable({ title, labelHeader, rows, shareHeader = "Share of invested" }) {
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
              <th>{shareHeader}</th>
              <th>Current value (Rs)</th>
              <th>P&amp;L (Rs)</th>
              <th>P&amp;L %</th>
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
                <td className={row.pnl < 0 ? "pnl-negative" : "pnl-positive"}>{pnlPercentText(row.pnl, row.invested)}</td>
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
export default function PortfolioAnalysis({ refreshKey, broker = "" }) {
  const [analysis, setAnalysis] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError("");
    getPortfolioAnalysis({ broker })
      .then((result) => {
        if (cancelled) return;
        setAnalysis(result);
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
  }, [refreshKey, broker]);

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
      {analysis.by_industry?.length > 0 && (
        <>
          <p className="analysis-summary">
            screener.in files some companies under a broad sector (for example Capital Goods); the
            industry view below splits them out (for example Aerospace &amp; Defense).
          </p>
          <BreakdownTable title="By industry" labelHeader="Industry" rows={analysis.by_industry} />
        </>
      )}
      {analysis.by_concentration?.length > 0 && (
        <>
          <p className="analysis-summary">
            Concentration: companies ranked by amount invested, largest first. The top tier is the
            few companies that make up the first 30% of your money, the core tier the next 60%, and
            the long tail the smallest holdings that make up the last 10%.
          </p>
          <BreakdownTable
            title="By concentration"
            labelHeader="Tier"
            rows={analysis.by_concentration}
          />
        </>
      )}
    </div>
  );
}
