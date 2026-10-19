import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { analyseCompany } from "../api/company";
import GrowthBarChart from "../components/charts/GrowthBarChart";
import ShareholdingChart from "../components/charts/ShareholdingChart";

const METRIC_LABELS = {
  Sales: "Sales",
  Operating_profit: "Operating Profit",
  OPM: "OPM %",
  Profit_before_tax: "Profit Before Tax",
  Net_Profit: "Net Profit",
  EPS: "EPS",
};

const TABS = ["Quarterly", "Yearly", "Shareholding"];

function errorMessage(err, fallback) {
  return err?.response?.data?.detail || fallback;
}

export default function CompanyDetail() {
  const location = useLocation();
  const navigate = useNavigate();
  const companyUrl = location.pathname;
  const passedName = location.state?.companyName;

  const [analysis, setAnalysis] = useState(null);
  const [activeTab, setActiveTab] = useState("Quarterly");
  const [reportType, setReportType] = useState("consolidated");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const hasConsolidated = !!analysis?.consolidated;
  // Default to consolidated when it exists (the fuller picture for groups
  // with subsidiaries); fall back to standalone for companies without one.
  const activeReport = useMemo(() => {
    if (!analysis) return null;
    return reportType === "consolidated" && hasConsolidated ? analysis.consolidated : analysis.standalone;
  }, [analysis, reportType, hasConsolidated]);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError("");
    analyseCompany(companyUrl, { companyName: passedName })
      .then((result) => {
        if (!cancelled) {
          setAnalysis(result);
          setReportType(result.consolidated ? "consolidated" : "standalone");
        }
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, "Could not analyse this company."));
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyUrl]);

  async function handleRefresh() {
    setIsLoading(true);
    setError("");
    try {
      const result = await analyseCompany(companyUrl, { companyName: passedName, forceRefresh: true });
      setAnalysis(result);
    } catch (err) {
      setError(errorMessage(err, "Could not refresh this company."));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="dashboard-page">
      <header className="dashboard-header">
        <h1>Dhan Varsha</h1>
        <button onClick={() => navigate(-1)}>Back</button>
      </header>
      <main>
        {isLoading && <p>Analysing company...</p>}
        {error && <p className="error-banner">{error}</p>}

        {analysis && (
          <>
            <div className="company-detail-header">
              <h2>{analysis.company_name}</h2>
              <button onClick={handleRefresh} disabled={isLoading}>
                Refresh
              </button>
            </div>
            {analysis.from_cache && (
              <p className="cache-banner">
                Showing cached data from {new Date(analysis.fetched_at).toLocaleString()}.
              </p>
            )}

            <div className="company-tabs">
              {TABS.map((tab) => (
                <button
                  key={tab}
                  className={`company-tab${activeTab === tab ? " active" : ""}`}
                  onClick={() => setActiveTab(tab)}
                >
                  {tab}
                </button>
              ))}
            </div>

            {(activeTab === "Quarterly" || activeTab === "Yearly") && (
              <div className="report-type-toggle">
                <button
                  type="button"
                  className={`report-type-option${reportType === "consolidated" ? " active" : ""}`}
                  onClick={() => setReportType("consolidated")}
                  disabled={!hasConsolidated}
                  title={hasConsolidated ? undefined : "No consolidated report published for this company"}
                >
                  Consolidated
                </button>
                <button
                  type="button"
                  className={`report-type-option${reportType === "standalone" ? " active" : ""}`}
                  onClick={() => setReportType("standalone")}
                >
                  Standalone
                </button>
                {!hasConsolidated && (
                  <span className="report-type-note">
                    No consolidated report published for this company - showing standalone only.
                  </span>
                )}
              </div>
            )}

            {activeTab === "Quarterly" && (
              <div className="chart-grid">
                {Object.entries(activeReport.quarterly.metrics).map(([metric, series]) => (
                  <div key={metric} className="chart-metric-section">
                    <GrowthBarChart
                      data={series.yoy}
                      title={`${METRIC_LABELS[metric] || metric} - Year over Year`}
                      groupByQuarter
                    />
                    <GrowthBarChart
                      data={series.qoq}
                      title={`${METRIC_LABELS[metric] || metric} - Quarter over Quarter`}
                    />
                  </div>
                ))}
              </div>
            )}

            {activeTab === "Yearly" && (
              <div className="chart-grid">
                {Object.entries(activeReport.yearly.metrics).map(([metric, series]) => (
                  <GrowthBarChart
                    key={metric}
                    data={series.change}
                    title={`${METRIC_LABELS[metric] || metric} - Yearly`}
                  />
                ))}
              </div>
            )}

            {activeTab === "Shareholding" && (
              <div className="chart-grid">
                <ShareholdingChart
                  periods={analysis.shareholding.quarterly.periods}
                  series={analysis.shareholding.quarterly.series}
                  title="Quarterly"
                />
                <ShareholdingChart
                  periods={analysis.shareholding.yearly.periods}
                  series={analysis.shareholding.yearly.series}
                  title="Yearly"
                />
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
