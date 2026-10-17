import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { downloadExport, fetchSectors, getJob, listJobs, runFetch } from "../api/screener";
import MetricsTable from "../components/MetricsTable";

function errorMessage(err, fallback) {
  return err?.response?.data?.detail || fallback;
}

export default function Dashboard() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const [sectors, setSectors] = useState([]);
  const [sectorKey, setSectorKey] = useState("");
  const [job, setJob] = useState(null);
  const [history, setHistory] = useState([]);
  const [isFetching, setIsFetching] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchSectors()
      .then(setSectors)
      .catch((err) => setError(errorMessage(err, "Could not load the sector list.")));
    refreshHistory();
  }, []);

  function refreshHistory() {
    listJobs().then(setHistory).catch(() => {});
  }

  async function handleAnalyze() {
    if (!sectorKey) return;
    setIsFetching(true);
    setError("");
    try {
      const result = await runFetch(sectorKey);
      setJob(result);
      refreshHistory();
    } catch (err) {
      setError(errorMessage(err, "Failed to fetch and analyse this sector."));
    } finally {
      setIsFetching(false);
    }
  }

  async function handleViewHistory(jobId) {
    setIsFetching(true);
    setError("");
    try {
      setJob(await getJob(jobId));
    } catch (err) {
      setError(errorMessage(err, "Failed to load that fetch job."));
    } finally {
      setIsFetching(false);
    }
  }

  async function handleExport() {
    if (!job) return;
    try {
      await downloadExport(job.id, `${job.sector_key}.xlsx`);
    } catch (err) {
      setError(errorMessage(err, "Failed to export the spreadsheet."));
    }
  }

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="dashboard-page">
      <header className="dashboard-header">
        <h1>Dhan Varsha</h1>
        <button onClick={handleLogout}>Log Out</button>
      </header>
      <main>
        <h2>Welcome, {user?.full_name}</h2>

        <section className="analyser-controls">
          <select value={sectorKey} onChange={(event) => setSectorKey(event.target.value)}>
            <option value="">Select a sector</option>
            {sectors.map((sector) => (
              <option key={sector.key} value={sector.key}>
                {sector.label}
              </option>
            ))}
          </select>
          <button onClick={handleAnalyze} disabled={!sectorKey || isFetching}>
            {isFetching ? "Analysing..." : "Fetch & Analyse"}
          </button>
          {job?.status === "success" && (
            <button onClick={handleExport}>Download Excel</button>
          )}
        </section>

        {error && <p className="error-banner">{error}</p>}

        {history.length > 0 && (
          <section className="analyser-history">
            <h3>Recent fetches</h3>
            <ul>
              {history.map((pastJob) => (
                <li key={pastJob.id}>
                  <button className="link-button" onClick={() => handleViewHistory(pastJob.id)}>
                    {pastJob.sector_label} - {new Date(pastJob.requested_at).toLocaleString()} (
                    {pastJob.status})
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}

        {job?.status === "success" && <MetricsTable job={job} />}
        {job?.status === "failed" && <p className="error-banner">{job.error_message}</p>}
      </main>
    </div>
  );
}
