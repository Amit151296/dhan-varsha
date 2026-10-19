// Shared chart tokens, following the dataviz skill's validated dark-mode
// categorical order and chrome roles, applied against this app's existing
// dark surfaces (#0f172a / #1e293b) rather than introducing a second theme.
export const CHART_SURFACE = "#1e293b";
export const GRID_COLOR = "#334155";
export const AXIS_COLOR = "#64748b";
export const TEXT_MUTED = "#94a3b8";
export const TEXT_PRIMARY = "#f1f5f9";

// Categorical slots 1-5 (dark steps) from the validated default palette -
// used for the shareholding stacked bars (Promoters/FIIs/DIIs/Government/Public).
export const CATEGORICAL = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"];

// Single sequential hue for magnitude bars (QoQ/YoY/yearly P&L).
export const METRIC_BAR_COLOR = "#3987e5";

// Reserved for "did this grow or shrink" text labels only - never a bar fill,
// so it never competes with the categorical/sequential rules above.
export const GROWTH_UP = "#4ade80";
export const GROWTH_DOWN = "#f87171";

export function growthColor(changePct) {
  if (changePct == null) return TEXT_MUTED;
  return changePct >= 0 ? GROWTH_UP : GROWTH_DOWN;
}
