import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { resolveCompanyByName } from "../api/company";

const ZONE_LABELS = {
  red: "Red",
  orange: "Orange",
  "light-green": "Light green",
  blue: "Blue",
  purple: "Purple",
  yellow: "Yellow",
  green: "Green",
};

function zoneLabel(zone) {
  return ZONE_LABELS[zone] || zone;
}

/** For each column, the distinct colour swatches present across all rows, in first-seen order. */
function buildColorOptionsByColumn(rows, columns) {
  const options = {};
  for (const column of columns) {
    const seen = new Map();
    for (const row of rows) {
      const highlight = row.highlights[column];
      if (highlight && !seen.has(highlight.zone)) {
        seen.set(highlight.zone, highlight);
      }
    }
    if (seen.size > 0) {
      options[column] = Array.from(seen.values());
    }
  }
  return options;
}

function ColorFilterMenu({ column, options, selectedZones, onToggle, onClear }) {
  const [open, setOpen] = useState(false);

  return (
    <span className="color-filter">
      <button
        type="button"
        className={`color-filter-toggle${selectedZones.size > 0 ? " active" : ""}`}
        onClick={() => setOpen((value) => !value)}
        aria-label={`Filter ${column} by colour`}
        title="Filter by colour"
      >
        ▾
      </button>
      {open && (
        <div className="color-filter-menu">
          {options.map((option) => (
            <label key={option.zone} className="color-filter-option">
              <input
                type="checkbox"
                checked={selectedZones.has(option.zone)}
                onChange={() => onToggle(column, option.zone)}
              />
              <span
                className="color-filter-swatch"
                style={{ backgroundColor: option.background }}
              />
              {zoneLabel(option.zone)}
            </label>
          ))}
          {selectedZones.size > 0 && (
            <button type="button" className="link-button color-filter-clear" onClick={() => onClear(column)}>
              Clear filter
            </button>
          )}
        </div>
      )}
    </span>
  );
}

export default function MetricsTable({ job }) {
  const navigate = useNavigate();
  const [colorFilters, setColorFilters] = useState({}); // { [column]: Set<zone> }
  const [selectedNames, setSelectedNames] = useState(() => new Set());
  const [compareOnly, setCompareOnly] = useState(false);
  const [resolvingName, setResolvingName] = useState(null);
  const [resolveError, setResolveError] = useState("");

  async function handleOpenCompany(name) {
    setResolvingName(name);
    setResolveError("");
    try {
      const company = await resolveCompanyByName(name);
      navigate(company.url, { state: { companyName: company.name } });
    } catch {
      setResolveError(`Could not find a screener.in page for "${name}".`);
    } finally {
      setResolvingName(null);
    }
  }

  const columns = useMemo(
    () => (job.rows.length ? Object.keys(job.rows[0].metrics) : []),
    [job.rows]
  );
  const colorOptionsByColumn = useMemo(
    () => buildColorOptionsByColumn(job.rows, columns),
    [job.rows, columns]
  );

  function toggleZone(column, zone) {
    setColorFilters((prev) => {
      const next = { ...prev };
      const current = new Set(next[column]);
      if (current.has(zone)) {
        current.delete(zone);
      } else {
        current.add(zone);
      }
      if (current.size === 0) {
        delete next[column];
      } else {
        next[column] = current;
      }
      return next;
    });
  }

  function clearColumnFilter(column) {
    setColorFilters((prev) => {
      const next = { ...prev };
      delete next[column];
      return next;
    });
  }

  function toggleRowSelection(name) {
    setSelectedNames((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      if (next.size === 0) {
        setCompareOnly(false);
      }
      return next;
    });
  }

  function clearSelection() {
    setSelectedNames(new Set());
    setCompareOnly(false);
  }

  const activeFilterColumns = Object.keys(colorFilters);
  const visibleRows = job.rows.filter((row) => {
    if (compareOnly && !selectedNames.has(row.name)) return false;
    return activeFilterColumns.every((column) => {
      const highlight = row.highlights[column];
      return highlight && colorFilters[column].has(highlight.zone);
    });
  });

  if (!job.rows.length) {
    return <p className="analyser-empty">No stocks matched this sector.</p>;
  }

  return (
    <div>
      {resolveError && <p className="error-banner">{resolveError}</p>}

      {selectedNames.size > 0 && (
        <div className="selection-summary">
          {selectedNames.size} compan{selectedNames.size === 1 ? "y" : "ies"} selected
          {" "}({Array.from(selectedNames).join(", ")}).{" "}
          <button type="button" className="link-button" onClick={() => setCompareOnly((value) => !value)}>
            {compareOnly ? "Show all rows" : "Compare selected only"}
          </button>{" "}
          <button type="button" className="link-button" onClick={clearSelection}>
            Clear selection
          </button>
        </div>
      )}

      {activeFilterColumns.length > 0 && (
        <div className="color-filter-summary">
          Showing {visibleRows.length} of {job.rows.length} rows filtered by colour.{" "}
          <button type="button" className="link-button" onClick={() => setColorFilters({})}>
            Clear all filters
          </button>
        </div>
      )}
      <div className="metrics-table-wrapper">
        <table className="metrics-table">
          <thead>
            <tr>
              <th className="metrics-table-sticky-checkbox" aria-label="Select for comparison" />
              <th className="metrics-table-sticky-col">Name</th>
              {columns.map((column) => (
                <th key={column}>
                  <span className="metrics-table-header-label">{column}</span>
                  {colorOptionsByColumn[column] && (
                    <ColorFilterMenu
                      column={column}
                      options={colorOptionsByColumn[column]}
                      selectedZones={colorFilters[column] || new Set()}
                      onToggle={toggleZone}
                      onClear={clearColumnFilter}
                    />
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row) => {
              const isSelected = selectedNames.has(row.name);
              return (
                <tr key={row.name} className={isSelected ? "row-selected" : undefined}>
                  <td className="metrics-table-sticky-checkbox">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleRowSelection(row.name)}
                      aria-label={`Select ${row.name} for comparison`}
                    />
                  </td>
                  <td className="metrics-table-sticky-col">
                    <button
                      type="button"
                      className="company-name-link"
                      onClick={() => handleOpenCompany(row.name)}
                      disabled={resolvingName === row.name}
                      title="View full company analysis"
                    >
                      {resolvingName === row.name ? `${row.name}...` : row.name}
                    </button>
                  </td>
                  {columns.map((column) => {
                    const highlight = row.highlights[column];
                    const style = highlight
                      ? { backgroundColor: highlight.background, color: highlight.color }
                      : undefined;
                    return (
                      <td key={column} style={style}>
                        {row.metrics[column]}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
            {visibleRows.length === 0 && (
              <tr>
                <td colSpan={columns.length + 2} className="analyser-empty">
                  No rows match the current filters/selection.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
