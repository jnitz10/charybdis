# Combined summary: Studies 1 and 2

Run date: 2026-07-10. This summary reports measurements, confidence intervals, and numeric interval-comparison statuses only.

## Study 1: off-hours versus RTH markout

The prior-#1 kill test uses net 30s passive-maker markout in bps, both sides pooled. Each cell is `point estimate (n, G; 95% cluster-bootstrap CI)`. “Overlap” or “separated” describes only the off-hours/RTH or weekend/RTH interval geometry.

| Market | RTH net 30s bps | Off-hours weekday net 30s bps | Weekend net 30s bps | CI status: off-hours / weekend vs RTH |
|---|---:|---:|---:|---|
| xyz:SP500 | -2.004 (n=245271, G=112; [-2.033, -1.974]) | -1.987 (n=270866, G=243; [-2.021, -1.957]) | -1.858 (n=100690, G=108; [-1.913, -1.797]) | overlap / separated, weekend above RTH by 0.061 bps |
| km:US500 | -2.442 (n=99922, G=122; [-2.490, -2.391]) | -2.432 (n=80842, G=264; [-2.516, -2.363]) | -2.098 (n=25104, G=116; [-2.294, -1.905]) | overlap / separated, weekend above RTH by 0.097 bps |
| flx:USA500 | -2.626 (n=1573, G=91; [-3.584, -1.632]) | -0.805 (n=1702, G=186; [-1.659, 0.021]) | 2.665 (n=767, G=75; [-2.428, 8.479]) | overlap / overlap |
| cash:USA500 | -2.245 (n=239518, G=122; [-2.284, -2.207]) | -2.180 (n=232098, G=264; [-2.222, -2.145]) | -2.240 (n=42376, G=117; [-2.363, -2.124]) | overlap / overlap |
| km:USTECH | -2.630 (n=39807, G=122; [-2.714, -2.546]) | -2.615 (n=27073, G=263; [-2.747, -2.495]) | -3.033 (n=4979, G=114; [-3.490, -2.471]) | overlap / overlap |
| xyz:XYZ100 | -2.178 (n=336215, G=122; [-2.208, -2.147]) | -2.117 (n=326770, G=264; [-2.164, -2.080]) | -2.154 (n=105838, G=117; [-2.280, -2.041]) | overlap / overlap |
| flx:USA100 | -3.921 (n=345, G=35; [-8.899, -0.898]) | -3.357 (n=350, G=64; [-15.750, 8.337]) | -12.071 (n=99, G=33; [-41.441, 16.635]) | overlap / overlap |
| km:SMALL2000 | -2.972 (n=10815, G=122; [-3.146, -2.785]) | -3.236 (n=9628, G=252; [-4.588, -1.929]) | -1.303 (n=1403, G=98; [-4.479, 2.814]) | overlap / overlap |

The L2 primary processed 694 market-days and 2,204,391 simulated fills. It assumes a 1.5 bps maker fee and a 60-second quote-age ceiling. The fill rule is an optimistic upper bound because prints do not expose cancellations ahead, hidden liquidity, or exact priority. In the overlap cross-check, L2/L4 trade-count agreement is 22.318% for flx:USA500 and 24.600% for flx:USA100; the other primary numbers remain the L2-era measurements described in the full report.

Sources: headline cells and statuses from `docs/reports/study1_offhours_markout_2026-07-09.md`, generated from `data/reports/study1_fills_l2.parquet` columns `market`, `segment`, `net_markout_30s_bps`, `stale_30s`, and `cluster_key`; run parameters from `data/reports/study1_run_meta.json` fields `market_days_processed`, `total_fills`, `maker_fee_bps`, and `max_quote_age_s`; overlap values from `data/reports/study1_overlap_l2_l4.json` market cluster fields `l2` and `l4` as summarized in the Study 1 report.

## Study 2: forced-flow proxy versus matched baseline

G2 found no liquidation, ADL, or forced-close action in HLSYSTEMEVENTS (0 of 1,070,342 audited rows), so all 1,367 SKHX and 1,206 SMSN events are heuristic `proxy-tagged` events rather than confirmed liquidations. The G2 census is recorded in `LEDGER.md` and is not duplicated in the regenerated report artifacts; proxy status and event counts are in `forced_flow_events_proxy.parquet`.

The primary 30s cells are:

| Market | Forced-flow net 30s bps | Baseline net 30s bps | Interval-comparison status |
|---|---:|---:|---|
| SKHX | -1.481 (n=98212, G=62; 95% CI [-2.054, -0.949]) | -1.602 (n=43540, G=73; 95% CI [-2.387, -0.991]) | overlap [-2.054, -0.991], width 1.063 bps |
| SMSN | -1.773 (n=35999, G=58; 95% CI [-2.434, -1.153]) | -2.599 (n=9979, G=59; 95% CI [-8.020, 1.195]) | overlap [-2.434, -1.153], width 1.282 bps |
| Pooled | -1.560 (n=134211, G=120; 95% CI [-2.010, -1.134]) | -1.788 (n=53519, G=132; 95% CI [-3.114, -0.853]) | overlap [-2.010, -1.134], width 0.876 bps |

The full Study 2 report gives all five horizons. Its coverage limitation is central: usable quotes end on 2026-06-18; 434 of 1,100 windows (39.5%) are dropped. Mean crossed-row fraction is 57.8% in forced-flow windows and 27.3% in baselines (+30.4 percentage points), selecting the forced-flow arm toward the calmer surviving subset. The comparison is therefore confounded and conservative as a documented measurement limitation. Anatomy is computed for 1,312 events; mean non-null reversion half-life is 116.779 seconds, with 96 censored events and 13 zero-overshoot events. Post-June-18 anatomy is coverage absent and untrustworthy.

Sources: 30s cells and coverage columns from `data/reports/forced_flow_vs_baseline_markout_proxy.parquet`; event counts from `data/reports/forced_flow_events_proxy.parquet` columns `market`, `trigger_source`, and `tag_label`; anatomy and coverage fields from `data/reports/forced_flow_analysis_meta_proxy.json` (`anatomy_computed_rows`, `reversion`, and `quote_coverage`). Full tables and column-level provenance are in `docs/reports/study2_forced_flow_2026-07-09.md`.

## Spend

The receipts-level meter total is $116.924738780 ($116.92 rounded): Study 1/T1 $70.661194624 + T5 $15.818600652 + T7 $30.444943504. This is $63.075261220 below the $180.00 cap. The per-day, per-SKU receipt and exact cross-check are in `docs/reports/spend_accounting_2026-07-09.md`; authoritative final fields are `data/spend.json` → `days.2026-07-10` and `running_cost_usd`.

## Open follow-ups

- **Markets gap (LOW):** `mkts` was absent from the flat-file listing even though the other requested markets were present. Confirm with CoinAPI whether this is a vendor coverage omission or an exchange/dataset naming issue before designing work that depends on `mkts` history.
- **Oracle start date (LOW):** the first observed oracle partition is 2026-06-17 16:00 UTC, but whether that timestamp is the actual feed inception remains unverified. Confirm the inception boundary with CoinAPI rather than treating the first listed object as proof of origin.
- **SKU billing verdict (MED):** the meter uses decimal GB and conservatively prices Hyperliquid-specific feeds at Trades tiers. Compare the per-SKU meter receipt with the CoinAPI console to confirm both GB versus GiB and the actual HL Oracle Prices / HL System Events SKU rates.
- **T6-1 substring-exception handling (LOW):** corrupt-gzip and missing-`user_taker` skips match exception message substrings. This is brittle to Polars message changes and over-broad when several columns are absent; replace it with structured error and column-set matching if revisited.
- **T7 residuals (LOW):** verify PENDING/REJECTED L4 depth semantics against a real cancel; keep post-June-18 depth excluded; make part-file writes atomic; and prevent `event_id` ordinal desynchronization when duplicate event keys occur.
- **Auto-recharge (LOW operational):** CoinAPI auto-recharge did not fire despite being enabled and caused the observed credit lockout. Escalate to CoinAPI support before another unattended paid pull.

Follow-up wording is collated from `LEDGER.md` deferred findings and T7 handoff notes; the ledger itself is unchanged.
