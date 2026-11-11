import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  getPortfolio,
  listPortfolioUploads,
  syncPortfolioPrices,
  uploadPortfolioScreenshot,
} from "../api/portfolio";
import PortfolioHoldingsTable from "../components/PortfolioHoldingsTable";
import AddHoldingForm from "../components/AddHoldingForm";
import PortfolioAnalysis from "../components/PortfolioAnalysis";

function errorMessage(err, fallback) {
  return err?.response?.data?.detail || fallback;
}

function formatCurrency(value) {
  return value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

export default function Portfolio() {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);

  const [portfolio, setPortfolio] = useState(null);
  const [history, setHistory] = useState([]);
  const [brokerLabel, setBrokerLabel] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null); // { current, total } | null
  const [skippedRows, setSkippedRows] = useState([]);
  const [readResults, setReadResults] = useState([]);
  const [isSyncing, setIsSyncing] = useState(false);
  const [unsynced, setUnsynced] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  function refreshHistory() {
    listPortfolioUploads().then(setHistory).catch(() => {});
  }

  function loadPortfolio() {
    setIsLoading(true);
    return getPortfolio()
      .then(setPortfolio)
      .catch((err) => setError(errorMessage(err, "Could not load your portfolio.")))
      .finally(() => setIsLoading(false));
  }

  useEffect(() => {
    loadPortfolio();
    refreshHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleFileChange(event) {
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (!files.length) return;

    setIsUploading(true);
    setError("");
    setSkippedRows([]);
    setReadResults([]);
    const failures = [];
    const skippedNames = new Set();
    const readSummaries = [];
    let latest = null;

    // One at a time: each upload merges into the same portfolio, so running them
    // in parallel could create duplicate rows for a stock that's on two screenshots.
    for (const [index, file] of files.entries()) {
      setUploadProgress({ current: index + 1, total: files.length });
      try {
        const result = await uploadPortfolioScreenshot(file, { broker: brokerLabel.trim() || undefined });
        latest = result;
        setPortfolio(result);
        result.skipped.forEach((name) => skippedNames.add(name));
        readSummaries.push(
          `${file.name}: ${result.upload_broker || "broker not recognised"}, ${result.upload_holdings} holding${result.upload_holdings === 1 ? "" : "s"}`
        );
      } catch (err) {
        failures.push(
          `${file.name}: ${errorMessage(err, "could not be read. Try a clearer, uncropped capture of the holdings screen.")}`
        );
      }
    }

    if (failures.length) {
      setError(
        `${failures.length} of ${files.length} screenshot${files.length === 1 ? "" : "s"} failed. ${failures.join(" | ")}`
      );
    }
    // A row cut off in one screenshot is usually fully visible in the next one; only
    // warn about names that still aren't in the portfolio after the whole batch.
    const present = new Set((latest?.holdings || []).map((h) => h.raw_name.toLowerCase()));
    setSkippedRows([...skippedNames].filter((name) => !present.has(name.toLowerCase())));
    setReadResults(readSummaries);
    refreshHistory();
    setUploadProgress(null);
    setIsUploading(false);
  }

  async function handleSync() {
    setIsSyncing(true);
    setError("");
    try {
      const result = await syncPortfolioPrices();
      setPortfolio(result);
      setUnsynced(result.unsynced || []);
    } catch (err) {
      setError(errorMessage(err, "Could not fetch the latest prices right now."));
    } finally {
      setIsSyncing(false);
    }
  }

  function handleHoldingsChange() {
    loadPortfolio();
  }

  function handleHoldingAdded() {
    loadPortfolio();
  }

  return (
    <div className="dashboard-page">
      <header className="dashboard-header">
        <h1>Dhan Varsha</h1>
        <button onClick={() => navigate("/dashboard")}>Back to Dashboard</button>
      </header>
      <main>
        <h2>My Portfolio</h2>
        <p>
          Upload screenshots of your holdings from Kite, Groww, Upstox, Angel One, or any other
          broker app. One screenshot often doesn&apos;t show every holding, and you can hold stocks
          across more than one broker - upload as many screenshots as you need and they&apos;ll all
          be merged into the single portfolio below. Click any company name to open its full
          analysis, and fix anything the screenshot read wrong by double-clicking a number.
        </p>

        <section className="analyser-controls">
          <input
            type="text"
            placeholder="Broker name (auto-detected if blank)"
            value={brokerLabel}
            onChange={(event) => setBrokerLabel(event.target.value)}
            style={{ width: "14rem" }}
          />
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            multiple
            onChange={handleFileChange}
            disabled={isUploading}
            style={{ display: "none" }}
          />
          <button onClick={() => fileInputRef.current?.click()} disabled={isUploading}>
            {isUploading
              ? `Reading screenshot ${uploadProgress?.current ?? 1} of ${uploadProgress?.total ?? 1}...`
              : "Upload portfolio screenshots"}
          </button>
          <button onClick={handleSync} disabled={isSyncing || !portfolio?.holdings.length}>
            {isSyncing ? "Syncing..." : "Sync prices"}
          </button>
        </section>

        {error && <p className="error-banner">{error}</p>}

        {readResults.length > 0 && (
          <p className="cache-banner">
            Read: {readResults.join(" | ")}. If a broker looks wrong, type its name in the broker box and
            upload that screenshot again.
          </p>
        )}

        {skippedRows.length > 0 && (
          <p className="error-banner">
            Skipped because they were cut off or unclear: {skippedRows.join(", ")}. Upload a screenshot
            where they are fully visible, or add them manually below.
          </p>
        )}

        {portfolio && (
          <p className="cache-banner">
            {portfolio.last_upload_at
              ? `Last uploaded on ${new Date(portfolio.last_upload_at).toLocaleString()}.`
              : "No screenshots uploaded yet - add holdings manually below, or upload one above."}{" "}
            {portfolio.last_synced_at
              ? `Prices last synced ${new Date(portfolio.last_synced_at).toLocaleString()}.`
              : "Prices not synced yet."}
          </p>
        )}

        {unsynced.length > 0 && (
          <p className="error-banner">
            Couldn&apos;t get a live price for: {unsynced.join(", ")}. Their values were left as they were.
          </p>
        )}

        {portfolio && portfolio.summary.holding_count > 0 && (
          <section className="selection-summary">
            {portfolio.summary.holding_count} holding{portfolio.summary.holding_count === 1 ? "" : "s"} - Invested: Rs{" "}
            {formatCurrency(portfolio.summary.total_invested)} - Current Value: Rs{" "}
            {formatCurrency(portfolio.summary.total_current_value)} - P&L: Rs{" "}
            {formatCurrency(portfolio.summary.total_pnl)}
            {" "}(compare these totals with your broker app; add, edit, or remove rows below until they match exactly)
          </section>
        )}

        {isLoading && <p>Loading your portfolio...</p>}
        {portfolio && <PortfolioHoldingsTable holdings={portfolio.holdings} onHoldingsChange={handleHoldingsChange} />}

        <h3>Bought or sold something? Update it here</h3>
        <p>
          No need to re-upload a screenshot. Add a company with the quantity and price you bought at
          (if you already hold it, the shares are added and your average price is blended), double-click
          a quantity to change it, or remove a company you&apos;ve sold.
        </p>
        <AddHoldingForm onAdded={handleHoldingAdded} />

        {portfolio && (
          <PortfolioAnalysis
            refreshKey={`${portfolio.summary.holding_count}-${portfolio.summary.total_invested}-${portfolio.holdings
              .map((h) => `${h.id}:${h.broker ?? ""}`)
              .join(",")}`}
          />
        )}

        {history.length > 0 && (
          <section className="analyser-history">
            <h3>Upload history</h3>
            <ul>
              {history.map((pastUpload) => (
                <li key={pastUpload.id}>
                  {new Date(pastUpload.uploaded_at).toLocaleString()}
                  {pastUpload.broker ? ` - ${pastUpload.broker}` : ""} - {pastUpload.status}
                  {pastUpload.status === "success" ? ` (${pastUpload.holdings_found} holdings read)` : ""}
                  {pastUpload.status === "failed" && pastUpload.error_message ? ` - ${pastUpload.error_message}` : ""}
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
    </div>
  );
}
