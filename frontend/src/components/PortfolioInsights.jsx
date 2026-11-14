import { useEffect, useState } from "react";
import { fetchPortfolioInsights } from "../api/portfolio";

function InsightList({ title, items, tone }) {
  return (
    <section className={`insight-column insight-${tone}`}>
      <h4>{title}</h4>
      {items.length === 0 && <p className="analyser-empty">Nothing stands out here.</p>}
      <ul>
        {items.map((item) => (
          <li key={item.title}>
            <strong>{item.title}</strong>
            {item.detail && <span> - {item.detail}</span>}
            {item.companies.length > 0 && (
              <span> ({item.companies.length} {item.companies.length === 1 ? "company" : "companies"})</span>
            )}
            {item.companies.length > 0 &&
              // Entries that carry their own figures with commas (net change, last quarter) get one line each;
              // plain names and short tags are comma separated.
              (item.companies.some((company) => company.includes(",")) ? (
                <ul className="insight-companies">
                  {item.companies.map((company) => (
                    <li key={company}>{company}</li>
                  ))}
                </ul>
              ) : (
                <div className="insight-companies">{item.companies.join(", ")}</div>
              ))}
          </li>
        ))}
      </ul>
    </section>
  );
}

// Reads the colour-coded table above it (via the backend) and lists what is strong and what is risky.
export default function PortfolioInsights({ jobId }) {
  const [insights, setInsights] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  // A new table means the old analysis no longer applies.
  useEffect(() => {
    setInsights(null);
    setError("");
  }, [jobId]);

  async function handleAnalyse({ refresh = false } = {}) {
    setIsLoading(true);
    setError("");
    try {
      setInsights(await fetchPortfolioInsights(jobId, { refresh }));
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not analyse the portfolio right now.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="analysis-section">
      <h3>Portfolio strength and risk</h3>
      <p className="analysis-summary">
        Reads the colour-coded table above: purple is best (white text on purple is the very best), red is risk,
        and yellow means data is missing, so it is left out of the judgement. It looks for strong sales and
        profit growth, low P/E and net buying by promoters, FIIs and DIIs as strengths, and pledged shares,
        debt above 0.5 and net selling as risks.
      </p>

      <button type="button" onClick={() => handleAnalyse()} disabled={isLoading}>
        {isLoading ? "Analysing..." : insights ? "Analyse again" : "Analyse strength and risk"}
      </button>

      {error && <p className="error-banner">{error}</p>}

      {insights && (
        <>
          {insights.source === "rules" && (
            <p className="error-banner">
              The AI summary isn&apos;t available ({insights.ai_error}). Showing the rule-based findings only.
            </p>
          )}
          {insights.summary && <p className="insight-summary">{insights.summary}</p>}

          <div className="insight-grid">
            <InsightList title="Strengths" items={insights.strengths} tone="strength" />
            <InsightList title="Risks" items={insights.risks} tone="risk" />
          </div>

          {insights.watchlist.length > 0 && (
            <section>
              <h4>Worth a closer look</h4>
              <ul>
                {insights.watchlist.map((entry) => (
                  <li key={entry}>{entry}</li>
                ))}
              </ul>
            </section>
          )}

          {insights.standouts.length > 0 && (
            <section>
              <h4>Companies with good points</h4>
              <ul>
                {insights.standouts.map((entry) => (
                  <li key={entry}>{entry}</li>
                ))}
              </ul>
            </section>
          )}

          <p className="analysis-summary">
            {insights.cached ? "Saved analysis" : "Generated"}
            {insights.generated_at ? ` from ${new Date(insights.generated_at).toLocaleString()}` : ""}. This is an
            automated reading of the table for analysis, not investment advice or a substitute for a financial
            adviser.{" "}
            {insights.cached && (
              <button type="button" className="link-button" onClick={() => handleAnalyse({ refresh: true })} disabled={isLoading}>
                Regenerate
              </button>
            )}
          </p>
        </>
      )}
    </div>
  );
}
