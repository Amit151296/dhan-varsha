// Must match NO_BROKER_LABEL in backend/app/services/portfolio/analysis.py.
export const NO_BROKER_LABEL = "Manual / not specified";

// Distinct broker names across holdings, with a trailing "no broker" option when some have none.
export function brokersFromHoldings(holdings) {
  const names = new Map();
  let hasNone = false;
  for (const h of holdings || []) {
    const name = (h.broker || "").trim();
    if (!name) hasNone = true;
    else if (!names.has(name.toLowerCase())) names.set(name.toLowerCase(), name);
  }
  const list = [...names.values()].sort((a, b) => a.localeCompare(b));
  if (hasNone) list.push(NO_BROKER_LABEL);
  return list;
}

export function filterByBroker(holdings, broker) {
  if (!broker) return holdings;
  return holdings.filter((h) => {
    const name = (h.broker || "").trim();
    return broker === NO_BROKER_LABEL ? !name : name.toLowerCase() === broker.toLowerCase();
  });
}

// Mirrors holding_amounts() in the backend so filtered totals match the unfiltered ones.
export function totalsFor(holdings) {
  let invested = 0;
  let current = 0;
  let pnl = 0;
  for (const h of holdings) {
    const inv = h.invested_value ?? (h.quantity && h.avg_price ? h.quantity * h.avg_price : 0);
    const cur = h.current_value ?? (h.quantity && h.ltp ? h.quantity * h.ltp : 0);
    invested += inv;
    current += cur;
    pnl += h.pnl ?? cur - inv;
  }
  return { invested, current, pnl };
}

export default function BrokerFilter({ brokers, value, onChange, disabled }) {
  if (!brokers || brokers.length < 2) return null; // nothing to filter with one broker
  return (
    <label className="broker-filter">
      Broker:{" "}
      <select value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled}>
        <option value="">All brokers</option>
        {brokers.map((b) => (
          <option key={b} value={b}>
            {b}
          </option>
        ))}
      </select>
    </label>
  );
}
