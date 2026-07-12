# Console feature request: backtest trade overlay on candle charts

**Requested:** 2026-07-11 (operator, during forced-flow harvester session)

## What

In the research console (`uv run charybdis-console`), load a candle chart for a
market and overlay a backtest's entries and exits on it, so backtests can be
examined visually trade-by-trade — where fills happened relative to the cascade,
where the exit landed, which knives were caught.

## Motivating use case

The forced-flow harvester backtests produce per-fill records that are exactly
this shape:

- `data/reports/ff_harvest_fills_all.parquet` — market, side, delta_bps,
  fill_time, fill_px, ref, markouts
- `data/reports/ff_passive_exit.parquet` — market, fill_time, policy, mode
  (passive/crossed), net_bps
- `data/reports/ff_minute_bars.parquet` + `data/reports/ff_bars/*.parquet` —
  per-minute lo/hi/med/n bars for the 13 tick-covered markets (candle source at
  minute resolution, finer than the hourly study3 candles)

Study-2 forced-flow events (`forced_flow_event_anatomy_proxy.parquet`) would
also make good overlay annotations (event windows, overshoot extents).

## Technical note — library choice

TradingView lightweight-charts **does support this**: the series-markers API
(`createSeriesMarkers` in v5, `series.setMarkers` in v4) pins arrows/shapes/
text to specific bars (e.g. `arrowUp` below-bar for entries, `arrowDown`
above-bar for exits, color by win/loss). Price lines (`createPriceLine`) can
show the resting-order level and reversion target. So **no library swap is
expected** — verify the installed version and use markers before evaluating
alternatives (ECharts / Plotly would be the fallbacks if something exotic like
connected entry→exit line segments per trade is required; those can also be
faked in lightweight-charts with a line series per trade or an overlay canvas).

## Sketch of the data contract

A "trade overlay" source = any parquet with at least:
`market, entry_time, entry_px, exit_time, exit_px, side, pnl_metric` —
console picks a market + overlay file, renders candles (existing sources or
ff_minute_bars) + entry/exit markers + optional per-trade tooltip (delta_bps,
mode, net_bps). Keep the loader generic so future backtests (Monday effect,
gated carry) plug in by writing a conforming parquet.

## Status

Backlog — not started. Recorded for a future console session; no code touched.
