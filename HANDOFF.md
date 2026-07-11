# HANDOFF — Research console: operator feedback fix round (2026-07-10)

The research console v1 (spec `docs/superpowers/specs/2026-07-10-research-console-design.md`)
merged to main at `952fa8e`. The operator then explored it and gave the feedback below.
This document is the work order for the fix round. Previous HANDOFF (Studies 1–2
orchestration) is superseded; see git history if needed.

## Process directives (operator-mandated, non-negotiable)

- **The superpowers plugin is UNINSTALLED.** Do not attempt its skills or workflow
  (brainstorm/writing-plans/subagent-driven-development are gone).
- **Load the `dataviz` skill BEFORE writing or editing ANY chart code**, and the
  `frontend-design:frontend-design` (or `compound-engineering:ce-frontend-design`) skill
  before frontend/visual work. This applies to code embedded in plans or subagent briefs
  too. The operator installed these specifically to be used and was rightly annoyed v1
  shipped without them. (Memory: `feedback-use-design-skills`.)
- Operator feedback style: blunt. The chart-reset bug got five HATEs. Treat items 1 and 2
  as the ones they actually care most about.

## How to run / verify

- `uv run charybdis-console` → http://localhost:8787 (serves `console/dist`)
- After frontend changes: `cd console && npm run build` (dev loop: `npm run dev`, proxies /api)
- Tests: `uv run pytest -q` (173 passed, 1 skipped at merge)
- Backend: `charybdis/console/` · Frontend: `console/src/` (pages/, charts/, api.ts, theme.ts, ui.tsx)
- Per-task review minors carried to "later": `.superpowers/sdd/progress.md` (gitignored scratch,
  survives until cleaned; the list was triaged acceptable-as-is by the final review)

## Feedback items (fix round scope)

### 1. Chart Lab resets zoom/pan on every indicator add/remove — operator HATES this (×5)
Root cause (already diagnosed): `console/src/charts/CandleChart.tsx` tears down and
recreates the whole lightweight-charts instance in a `useEffect` keyed on all data props,
then calls `chart.timeScale().fitContent()`. Adding an indicator → new candles payload →
full re-init → viewport reset.
Fix direction: keep the chart instance alive across renders (create once per mount);
diff series in/out (add/remove indicator series without touching the candle series);
preserve the visible time range (`timeScale().getVisibleLogicalRange()` → restore after
data updates); only `fitContent()` on first load or market/source change.
`TimeSeriesChart.tsx` has the same rebuild pattern (less painful, fix while in there).

### 2. Raw CoinAPI data is not browsable — "the whole fucking point" (headline item)
v1 scoped the console to `data/reports/*.parquet` only (non-recursive, parquet-only glob
in `charybdis/console/datasets.py`). Invisible today:
- `data/T-TRADES/`, `data/T-QUOTES/`, `data/T-LIMITBOOK_FULL/` (15G), `data/T-HLORACLEPRICES/`,
  `data/T-HLSYSTEMEVENTS/` — ~21.5 GB raw CoinAPI flat files, day-partition dirs
  (`D-2026070621/`) of gzipped CSVs (schema note: `;`-separated, see study pull code
  `charybdis/loaders.py` + `data/study1_manifest.json` for structure)
- Subdirs inside `data/reports/` (`study1_l2_parts/`, `study1_l2_stats/`,
  `study2_markout_parts_proxy/` — hundreds of per-day part files)
- Loose parquets outside reports/ (e.g. `data/study2_funding.parquet`)
Fix direction: recursive/partitioned dataset discovery; lazy polars scan of gzip CSVs
(never load 15 GB); day-partition navigation UI in the Data Browser; ideally Chart Lab
gains a raw-trades candle source (build OHLCV from T-TRADES server-side) so anything
pulled can be charted, not just the study3 REST harvest. Existing `charybdis/loaders.py`
already knows how to read these files — reuse it, don't reinvent.

### 3. Per-chart explanations — non-intrusive, click-a-`?` popover
Every chart gets a small `?` icon next to its title; clicking opens a popover with:
what the chart shows, how to read it (e.g. "whiskers = 95% cluster-bootstrap CIs;
overlapping intervals = no separation"), what conclusion it feeds, and domain-term
glossary (proxy events, KRX frozen, dex prefixes, market symbols). Nothing visible
until clicked. Content sourced from the study reports in `docs/reports/`.

### 4. Dot-whisker color bug: legend says green, dots are gray
Study 2 "Forced-flow proxy vs matched baseline" and Study 3 "Funding-clock brackets vs
baseline" charts. Root cause: in `console/src/charts/options.ts` `dotWhisker()`, each
group = custom series (whiskers) + scatter series sharing one name; the legend takes its
swatch from the first series (the custom one, which has no `itemStyle.color`) → ECharts
default palette green in the legend, while dots are painted `C.muted` gray. Fix: set the
group color on BOTH series; give baseline a real color from the dataviz-skill palette
instead of gray (operator expected green).

### 5. Visual redo under dataviz + frontend-design skills
Re-audit all charts and page styling against the `dataviz` skill (palette, mark specs,
legend/tooltip rules, stat tiles) and frontend-design guidance — not just patching the
specific bugs above. v1's look is "competent generic dark dashboard"; operator wants
genuinely good. The "looks really good" visual gate has still never been signed off.

### 6. Market-symbol clarity (from Q&A during exploration; fold into #3 or Chart Lab)
Facts established (verified live against HL API + local snapshots, 2026-07-10):
- `SMSN` = Samsung Electronics (GDR ticker), `SKHX` = SK Hynix — Korean HIP-3 perps;
  studies condition on KRX (Korea Exchange) open/frozen state because of this.
- `xyz:SKHX` and `xyz:SKHY` are TWO DISTINCT live assets (different oracle px 1474.7 vs
  169.39, different OI caps $1B vs $250M) — likely re-listing at a different unit scale,
  same wart as km:US500 vs xyz:SP500 in Study 3.
- The Hyperliquid app displays deployer-set display names (`setPerpAnnotation` action in
  the dex registry) like "xyz:SKHYNIX"; the immutable on-chain asset code (`SKHX`) is what
  the API, CoinAPI, and all our data use. Code ≠ app label; a Chart Lab "market info"
  affordance (oracle px, OI cap, dex, aliases) would defuse this recurring confusion.

## Suggested order

1 and 4 are small and rage-inducing — fix first for quick wins (load `dataviz` before
touching them). Then 2 (the headline, largest item). Then 3 + 6 together (popover system).
5 runs as the lens over all of it, with a screenshot-verified pass at the end.

## Not in scope (unless operator asks)

- The carried review minors in `.superpowers/sdd/progress.md` (all triaged acceptable)
- echarts 5.x npm advisory (plan-pinned)
- notebook-intelligence labextension version warning (stale metadata; upstream supports
  JupyterLab ≥4.5.7). RESOLVED: operator tested notebooks 2026-07-10 — working, including
  the Ctrl+G inline per-cell prompting flow (documented in notebooks/README.md). No action.
