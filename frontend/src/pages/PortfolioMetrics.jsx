import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchPortfolioMetrics, getPortfolio } from "../api/portfolio";
import { downloadExport } from "../api/screener";
import BrokerFilter, { brokersFromHoldings } from "../components/BrokerFilter";
import DownloadMenu from "../components/DownloadMenu";
import MetricsTable from "../components/MetricsTable";
import PortfolioInsights from "../components/PortfolioInsights";
import { useAuth } from "../context/AuthContext";

function errorMessage(err, fallback) {
  return err?.response?.data?.detail || fallback;
}

export default function PortfolioMetrics() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const owner = user?.full_name ? `${user.full_name}'s` : "My";
  const [job, setJob] = useState(null);
  const [isFetching, setIsFetching] = useState(false);
  const [error, setError] = useState("");
  const [brokers, setBrokers] = useState([]);
  const [broker, setBroker] = useState("");

  useEffect(() => {
    getPortfolio()
      .then((p) => setBrokers(brokersFromHoldings(p.holdings)))
      .catch(() => {});
  }, []);

  function handleBrokerChange(value) {
    setBroker(value);
    setJob(null); // the shown table belongs to the previous filter
    setError("");
  }

  async function handleFetch({ forceRefresh = false } = {}) {
    setIsFetching(true);
    setError("");
    try {
      setJob(await fetchPortfolioMetrics({ forceRefresh, broker }));
    } catch (err) {
      setError(errorMessage(err, "Could not fetch metrics for your portfolio companies."));
    } finally {
      setIsFetching(false);
    }
  }

  async function handleExport(format) {
    try {
      const base = `${owner.replace(/\W+/g, "_")}_portfolio${broker ? `_${broker.replace(/\W+/g, "_")}` : ""}`;
      await downloadExport(job.id, `${base}.${format}`, format);
    } catch (err) {
      setError(errorMessage(err, "Failed to export the spreadsheet."));
    }
  }

  return (
    <div className="dashboard-page">
      <header className="dashboard-header">
        <h1>Dhan Varsha</h1>
        <button onClick={() => navigate("/portfolio")}>Back to Portfolio</button>
      </header>
      <main>
        <h2>{owner} portfolio - company metrics</h2>
        <p>
          Growth, returns, valuation, and shareholding metrics from screener.in for the companies in
          your portfolio. This is only fetched when you click the button below, so opening your
          portfolio stays fast and doesn&apos;t make extra calls.
        </p>

        <section className="analyser-controls">
          <BrokerFilter brokers={brokers} value={broker} onChange={handleBrokerChange} disabled={isFetching} />
          <button onClick={() => handleFetch()} disabled={isFetching}>
            {isFetching ? "Fetching..." : "Fetch metrics"}
          </button>
          {job?.status === "success" && <DownloadMenu label="Download" onDownload={handleExport} />}
        </section>

        {isFetching && (
          <p className="cache-banner">
            Fetching from screener.in. The first time can take a few minutes for a large portfolio; after
            that each company is saved and loads instantly for everyone.
          </p>
        )}

        {error && <p className="error-banner">{error}</p>}

        {job?.status === "success" && job.from_cache && (
          <p className="cache-banner">
            Showing cached data from {new Date(job.completed_at).toLocaleString()} (this analysis data is saved
            and shared, and only refreshed from screener.in about once a week).{" "}
            <button
              type="button"
              className="link-button"
              onClick={() => handleFetch({ forceRefresh: true })}
              disabled={isFetching}
            >
              Refresh now
            </button>
          </p>
        )}

        {job?.status === "success" && <MetricsTable job={job} />}
        {job?.status === "success" && job.rows.length > 0 && <PortfolioInsights jobId={job.id} />}
      </main>
    </div>
  );
}
