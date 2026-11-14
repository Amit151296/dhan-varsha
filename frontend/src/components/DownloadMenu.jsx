import { useState } from "react";

// One "Download" button that lets the user pick a file type. `onDownload(format)` does the work.
export default function DownloadMenu({ label = "Download", onDownload, disabled }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function pick(format) {
    setOpen(false);
    setBusy(true);
    try {
      await onDownload(format);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="download-menu" style={{ position: "relative", display: "inline-block" }}>
      <button type="button" onClick={() => setOpen((value) => !value)} disabled={disabled || busy}>
        {busy ? "Preparing..." : `${label} ▾`}
      </button>
      {open && (
        <div
          className="color-filter-menu"
          style={{ display: "flex", flexDirection: "column", gap: "0.25rem", minWidth: "15rem", zIndex: 5 }}
        >
          <button type="button" className="link-button" onClick={() => pick("xlsx")}>
            Excel file (.xlsx) - for laptop
          </button>
          <button type="button" className="link-button" onClick={() => pick("html")}>
            Web page (.html) - opens on phone or laptop
          </button>
        </div>
      )}
    </span>
  );
}
