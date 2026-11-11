import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { resolveCompanyByName } from "../api/company";
import { deleteHolding, updateHolding } from "../api/portfolio";

const EDITABLE_COLUMNS = [
  { key: "quantity", label: "Qty" },
  { key: "avg_price", label: "Avg. Price" },
  { key: "ltp", label: "LTP" },
  { key: "invested_value", label: "Invested" },
  { key: "current_value", label: "Current Value" },
  { key: "pnl", label: "P&L" },
];

function formatNumber(value) {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function EditableCell({ holding, column, onSaved }) {
  const [isEditing, setIsEditing] = useState(false);
  const [value, setValue] = useState(holding[column.key] ?? "");
  const [isSaving, setIsSaving] = useState(false);

  async function handleSave() {
    setIsSaving(true);
    try {
      const parsed = value === "" ? null : Number(value);
      const updated = await updateHolding(holding.id, { [column.key]: parsed });
      onSaved(updated);
      setIsEditing(false);
    } finally {
      setIsSaving(false);
    }
  }

  if (!isEditing) {
    const isApproximate = column.key === "ltp" && holding.price_is_approximate;
    return (
      <td
        onDoubleClick={() => {
          setValue(holding[column.key] ?? "");
          setIsEditing(true);
        }}
        title={
          isApproximate
            ? "Approximate - screener.in's quoted price, used because a live market quote wasn't available. Double-click to edit."
            : "Double-click to edit"
        }
      >
        {isApproximate && <span className="approx-marker">~</span>}
        {formatNumber(holding[column.key])}
      </td>
    );
  }

  return (
    <td>
      <input
        type="number"
        value={value}
        autoFocus
        disabled={isSaving}
        onChange={(event) => setValue(event.target.value)}
        onBlur={handleSave}
        onKeyDown={(event) => {
          if (event.key === "Enter") handleSave();
          if (event.key === "Escape") setIsEditing(false);
        }}
        style={{ width: "6.5rem" }}
      />
    </td>
  );
}

function sortHoldings(holdings, sort) {
  if (!sort) return holdings;
  const direction = sort.direction === "asc" ? 1 : -1;
  return [...holdings].sort((a, b) => {
    const left = a[sort.key];
    const right = b[sort.key];
    // Empty values always sink to the bottom, whichever way we're sorting.
    if (left == null && right == null) return 0;
    if (left == null) return 1;
    if (right == null) return -1;
    if (typeof left === "string") return left.localeCompare(right) * direction;
    return (left - right) * direction;
  });
}

export default function PortfolioHoldingsTable({ holdings, onHoldingsChange }) {
  const navigate = useNavigate();
  const [sort, setSort] = useState(null); // { key, direction } | null

  function toggleSort(key) {
    setSort((prev) => {
      if (!prev || prev.key !== key) return { key, direction: key === "raw_name" ? "asc" : "desc" };
      if (prev.direction === "desc" && key !== "raw_name") return { key, direction: "asc" };
      if (prev.direction === "asc" && key === "raw_name") return { key, direction: "desc" };
      return null;
    });
  }

  function sortIndicator(key) {
    if (sort?.key !== key) return "";
    return sort.direction === "asc" ? " ▲" : " ▼";
  }

  const sortedHoldings = sortHoldings(holdings, sort);
  const [resolvingName, setResolvingName] = useState(null);
  const [resolveError, setResolveError] = useState("");
  const [deletingId, setDeletingId] = useState(null);

  async function handleOpenCompany(holding) {
    if (holding.resolved_url) {
      navigate(holding.resolved_url, { state: { companyName: holding.resolved_name } });
      return;
    }
    setResolvingName(holding.raw_name);
    setResolveError("");
    try {
      const company = await resolveCompanyByName(holding.raw_name);
      navigate(company.url, { state: { companyName: company.name } });
    } catch {
      setResolveError(`Could not find a screener.in page for "${holding.raw_name}".`);
    } finally {
      setResolvingName(null);
    }
  }

  function handleCellSaved(updated) {
    onHoldingsChange(holdings.map((h) => (h.id === updated.id ? updated : h)));
  }

  async function handleDelete(holding) {
    setDeletingId(holding.id);
    try {
      await deleteHolding(holding.id);
      onHoldingsChange(holdings.filter((h) => h.id !== holding.id));
    } finally {
      setDeletingId(null);
    }
  }

  if (!holdings.length) {
    return <p className="analyser-empty">Your portfolio is empty. Upload a screenshot or add a company below.</p>;
  }

  return (
    <div>
      {resolveError && <p className="error-banner">{resolveError}</p>}
      <div className="metrics-table-wrapper">
        <table className="metrics-table portfolio-table">
          <thead>
            <tr>
              <th className="metrics-table-sticky-col">
                <button type="button" className="link-button" onClick={() => toggleSort("raw_name")}>
                  Company{sortIndicator("raw_name")}
                </button>
              </th>
              <th>Broker</th>
              {EDITABLE_COLUMNS.map((column) => (
                <th key={column.key}>
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => toggleSort(column.key)}
                    title={`Sort by ${column.label}`}
                  >
                    {column.label}
                    {sortIndicator(column.key)}
                  </button>
                </th>
              ))}
              <th aria-label="Delete" />
            </tr>
          </thead>
          <tbody>
            {sortedHoldings.map((holding) => (
              <tr key={holding.id}>
                <td className="metrics-table-sticky-col">
                  <button
                    type="button"
                    className="company-name-link"
                    onClick={() => handleOpenCompany(holding)}
                    disabled={resolvingName === holding.raw_name}
                    title={holding.resolved_name || "View full company analysis"}
                  >
                    {resolvingName === holding.raw_name ? `${holding.raw_name}...` : holding.raw_name}
                  </button>
                </td>
                <td>{holding.broker || "-"}</td>
                {EDITABLE_COLUMNS.map((column) => (
                  <EditableCell key={column.key} holding={holding} column={column} onSaved={handleCellSaved} />
                ))}
                <td>
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => handleDelete(holding)}
                    disabled={deletingId === holding.id}
                  >
                    {deletingId === holding.id ? "Removing..." : "Remove"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="analyser-empty" style={{ textAlign: "left" }}>
        Double-click any number to correct it (e.g. to match your broker app exactly).
      </p>
    </div>
  );
}
