import { useState } from "react";
import CompanySearchBox from "./CompanySearchBox";
import { addHolding } from "../api/portfolio";

export default function AddHoldingForm({ onAdded }) {
  const [company, setCompany] = useState(null);
  const [quantity, setQuantity] = useState("");
  const [avgPrice, setAvgPrice] = useState("");
  const [error, setError] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  async function handleAdd() {
    if (!company) {
      setError("Search and select a company first.");
      return;
    }
    setIsSaving(true);
    setError("");
    try {
      const holding = await addHolding({
        company_name: company.name,
        resolved_name: company.name,
        resolved_url: company.url,
        quantity: quantity === "" ? null : Number(quantity),
        avg_price: avgPrice === "" ? null : Number(avgPrice),
      });
      onAdded(holding);
      setCompany(null);
      setQuantity("");
      setAvgPrice("");
    } catch (err) {
      setError(err?.response?.data?.detail || "Could not add this holding.");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="analyser-controls" style={{ alignItems: "flex-start", flexWrap: "wrap" }}>
      <div style={{ minWidth: "16rem" }}>
        <CompanySearchBox onSelect={setCompany} placeholder="Add a company to your portfolio..." />
      </div>
      <input
        type="number"
        placeholder="Qty"
        value={quantity}
        onChange={(event) => setQuantity(event.target.value)}
        style={{ width: "6rem" }}
      />
      <input
        type="number"
        placeholder="Avg. price"
        value={avgPrice}
        onChange={(event) => setAvgPrice(event.target.value)}
        style={{ width: "7rem" }}
      />
      <button onClick={handleAdd} disabled={isSaving}>
        {isSaving ? "Adding..." : "Add holding"}
      </button>
      {error && <p className="error-banner">{error}</p>}
    </div>
  );
}
