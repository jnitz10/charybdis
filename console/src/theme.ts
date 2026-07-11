/** Single source of truth for console colors (dark theme only). */

// Categorical series palette in fixed assignment order (blue, aqua, yellow, green,
// violet, red, magenta, orange). Validated for the dark panel surface (#18181b):
// OKLCH lightness band, chroma floor, CVD adjacent-pair separation, >=3:1 contrast.
// Assign slots in sequence; never reorder, insert, or cycle.
const SERIES = [
  '#3987e5',
  '#199e70',
  '#c98500',
  '#008300',
  '#9085e9',
  '#e66767',
  '#d55181',
  '#d95926',
]

/** Data face — numerals, axes, tables, stats. Prose stays in the body sans. */
export const MONO =
  "ui-monospace, 'SF Mono', 'Cascadia Mono', 'JetBrains Mono', Menlo, Consolas, monospace"

export const C = {
  bg: '#09090b',
  panel: '#18181b',
  border: '#27272a',
  // chart gridlines sit a step below the UI border so marks stay in front
  grid: '#1f1f23',
  text: '#d4d4d8',
  muted: '#71717a',
  accent: '#22d3ee',
  up: '#10b981',
  down: '#f43f5e',
  series: SERIES,
  // Control/baseline groups in CI charts always wear green (entity-stable color).
  baseline: SERIES[3],
}
