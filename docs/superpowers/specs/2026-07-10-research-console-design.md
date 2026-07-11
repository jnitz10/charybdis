# Charybdis Research Console + AI Notebooks — Design

**Date:** 2026-07-10
**Status:** Approved by operator (brainstorming session)

## Goal

Two deliverables:

1. **Research console** — a living, local web dashboard that visualizes what the
   study reports found, with genuinely good-looking interactive charts. Starts
   with one command, reads the parquet tables in `data/reports/` directly, and
   grows incrementally as new studies land.
2. **AI notebooks** — JupyterLab wired to Claude Code via the
   [notebook-intelligence](https://github.com/plmbr/notebook-intelligence)
   extension (Claude mode), so the operator can type what they want in a chat
   panel and get code inserted into the notebook.

## Non-goals

- No remote deployment, auth, or multi-user anything. Local only.
- No parsing of the markdown reports. Overview content is hand-curated.
- No writes to `data/` from the console. Read-only.
- No re-running of studies from the UI. The console visualizes existing outputs.

## Part 1: Research console

### Architecture

- **Backend** — `charybdis/console/` inside the existing Python package.
  FastAPI + uvicorn. Reads `data/reports/*.parquet` with polars lazy scans;
  in-process cache keyed by `(path, mtime)`. New `[project.scripts]` entry
  `charybdis-console` so the whole app starts with `uv run charybdis-console`
  and serves at `http://localhost:8787`.
- **Frontend** — `console/` at repo root. Vite + React + TypeScript + Tailwind,
  dark theme by default. The production build output is served as static files
  by the FastAPI app, so daily use remains the single command. During frontend
  development, `npm run dev` proxies `/api` to the backend.
- **Charting** — hybrid:
  - **lightweight-charts** (TradingView, MIT) for candlesticks and equity
    curves — trading-terminal look, crosshair, panning, indicator panes.
  - **Apache ECharts** for everything else — markout curves, heatmaps,
    distributions, scatters.

### Resilience

`data/` is 22 GB and gitignored; not every checkout has every table. Any view
whose backing parquet is missing renders an explicit "dataset not present"
state instead of erroring. Large tables are paginated or downsampled
server-side before hitting the browser.

### Views (v1)

1. **Overview** — landing page telling the story so far: one card per study
   with headline conclusion, key numbers, verdict, and links to detail pages.
   Content lives in a curated YAML registry at
   `charybdis/console/findings.yaml`, deliberately hand-written. Adding Study 4 later is a small
   edit to that file plus optional new views.
2. **Study 1–2 pages** — off-hours markout curves by horizon/session
   (`study1_*` tables); forced-flow event anatomy, vs-baseline fills/markout
   comparisons, depth samples and quote coverage (`forced_flow_*`, `study2_*`
   tables).
3. **Study 3 pages** — funding census distributions (`study3_sa_census`),
   carry backtest (`study3_sc_backtest`, `study3_sc_summary`), funding-clock
   brackets (`study3_sd_brackets`), cross-dex spreads (`study3_se_spreads`),
   funding→forced-flow hazard (`study3_sf_*`).
4. **Chart Lab** — candlestick viewer. Pick data source + symbol + timeframe
   (v1 sources: `study3_candles_1h`, `study3_candles_1d`; source list is a
   registry, extensible). Toggle indicators from the indicator registry.
   Overlays (EMA, Bollinger, VWAP) render on the price chart; oscillators
   (RSI, MACD) get their own panes below.
5. **Backtest viewer** — a generic component, not a Study-3 one-off. Input: a
   results table matching a light schema (timestamp, equity, optional
   returns/positions/trades). Output: equity curve, drawdown chart, rolling
   Sharpe, monthly-return heatmap, summary stat cards. The Study 3 carry
   backtest is the first registered instance; future backtests register a
   parquet path and appear automatically.
6. **Data browser** — every parquet in `data/reports/`: schema, row count,
   paginated + filterable table view, quick x-vs-y scatter/line plot. The
   fallback for tables without a dedicated view.

### Indicator system

Server-side, registry-based, one function per indicator:

```python
@indicator("ema", params={"period": 20}, display="overlay")
def ema(ohlcv: pl.DataFrame, period: int) -> pl.Series: ...
```

The registry drives the API (`GET /api/candles?source=…&symbol=…&tf=…&ind=ema:20,rsi:14`),
the Chart Lab's indicator picker (auto-populated with names + params), and
overlay-vs-pane placement. Adding an indicator = one Python function, zero
frontend changes. V1 ships: SMA, EMA, RSI, MACD, Bollinger Bands, VWAP, ATR.

### API surface (sketch)

- `GET /api/findings` — curated overview content
- `GET /api/datasets` — parquet inventory (path, schema, rows, mtime, present/absent)
- `GET /api/datasets/{name}/rows?filter=…&page=…` — data browser
- `GET /api/candles?source=…&symbol=…&tf=…&ind=…` — Chart Lab
- `GET /api/indicators` — indicator registry metadata
- `GET /api/backtests` / `GET /api/backtests/{id}` — backtest viewer
- Study-specific endpoints as needed (markout curves, census, spreads…), all
  thin polars queries over the existing tables.

## Part 2: Notebooks + Claude Code

- Add a `dev` dependency group to `pyproject.toml`: `jupyterlab`,
  `notebook-intelligence`, `ipykernel`.
- Create `notebooks/` with a starter notebook demonstrating: loading report
  parquets with polars, using `charybdis.loaders`, and a quick plot.
  Gitignore `.ipynb_checkpoints/`.
- **Notebook Intelligence, Claude mode**: NBI's chat panel launches the
  operator's actual Claude Code CLI inside JupyterLab — full toolset, skills,
  MCP servers, project context — and can create/edit notebook cells from chat.
  Inline tab-completions additionally require an `ANTHROPIC_API_KEY`; that
  part is optional. Configuration is via NBI's GUI settings dialog (persists
  in `~/.jupyter/nbi/config.json`); exact steps documented in
  `notebooks/README.md`.

## Testing

- **Backend (pytest, existing `tests/` conventions):** golden-value tests for
  every indicator; API endpoint tests via FastAPI TestClient against tiny
  fixture parquets committed to the repo (a few KB each); missing-dataset
  behavior test (absent parquet → clean 404/absent flag, not a 500).
- **Frontend:** `tsc --noEmit` + `vite build` as the gate. No component-test
  suite in v1.

## Build order (high level, for the implementation plan)

1. Backend skeleton: FastAPI app, dataset registry, `charybdis-console` entry
   point, static-file serving, fixture-backed tests.
2. Frontend skeleton: Vite/React/Tailwind shell, dark theme, nav, API client.
3. Data browser (exercises the generic dataset plumbing end to end).
4. Indicator registry + Chart Lab.
5. Backtest viewer (generic) + Study 3 carry as first instance.
6. Study 1–2 and Study 3 detail pages.
7. Overview page + findings YAML.
8. Notebooks: deps, starter notebook, NBI setup docs.
