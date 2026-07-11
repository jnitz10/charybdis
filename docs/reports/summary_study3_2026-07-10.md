# Combined summary: Study 3 funding deep dive

Run date: 2026-07-10. This summary reports measurements, confidence intervals, pre-registered falsification-criterion statuses, and numeric interval geometry only. `NULL` is the pre-registered label for an interval containing zero; operator adjudication is outside this report.

## S-A: funding census and persistence (F-A)

The snapshot contains 225 HIP-3 markets plus 3 main-dex references. Across all 228 harvested series, coverage is 105 complete, 78 candle-truncated, 0 funding-truncated, and 45 no-data; the funding census has 183 data-bearing series. The top three mean APRs are xyz:SHAZ 203.21% (95% CI [123.42%, 284.18%]), vntl:OPENAI 187.24% ([107.47%, 281.72%]), and vntl:ANTHROPIC 143.86% ([93.66%, 201.06%]). Among 181 defined stationary half-lives, the median is 1.30h and maximum is 9.93h. F-A: 0/183 are `carry_relevant`; the pre-registered 24h half-life bar is structurally unreachable at hourly cadence because it requires AR(1) phi at least 0.9715 while the observed maximum is 0.9326. The frozen S-C universe has 67 markets above the $1,000,000 day-volume floor.

Provenance: `study3_snapshots.parquet: dex` (225 non-main, 3 main); `study3_sa_census.parquet: coverage_complete_count=105, coverage_candle_truncated_count=78, coverage_funding_truncated_count=0, coverage_no_data_count=45, market, mean_apr, mean_apr_ci_low, mean_apr_ci_high, shock_half_life_hours, ar1_phi, carry_half_life_threshold_hours=24, carry_relevant_count=0`; `study3_universe.parquet: passes_liquidity_floor=true` (67), `liquidity_floor_usd=1000000`. The phi requirement 0.9715 is the transformation of the parquet's 24h threshold documented in `study3_funding_census_2026-07-10.md`.

Key caveats: current snapshot OI and day volume are size proxies, not historical executable depth; candle truncation does not remove funding observations; no-data markets have no census statistic; weekly rank histories vary with inception.

## S-B: funding mechanics (F-B)

The 986-hour feed reconciliation gives mechanical-formula R² 0.99291893 and raw-premium R² 0.99570558. The fitted affine slope is 1.13387994, equivalent to an approximately 13% multiplicative identity gap relative to the configured multiplier, so the prediction is not an absolute funding-level estimate. Intra-hour `observed / iid_floor / iid_excess` R² is 0.31613548 / 0.01773390 / 0.29840159 at minute 0, 0.58029150 / 0.18231963 / 0.39797187 at minute 10, and 0.96215113 / 0.84477691 / 0.11737422 at minute 50. F-B input: minute-50 observed R² = 0.96215113; 50/60 minutes of the averaging window have already been observed, while minute 10 is the 50-minute-lead measurement.

Provenance: `study3_sb_reconciliation.parquet: record_type, average_premium, predicted_funding, realized_funding` (986 hourly rows; regressions), and minute-curve columns `minute, observed_r2, iid_floor, iid_excess, hour_count`. The affine scale is recomputed from those hourly columns and documented in `study3_mechanics_2026-07-10.md`.

Key caveats: the oracle feed covers about three weeks and only SKHX/SMSN; SP500 is excluded because bare oracle identifiers collide across dexes; the approximately 13% affine scale prevents absolute-level consumption.

## S-C: cross-sectional carry (F-C)

| Strategy | Net return (95% CI) | Sharpe (95% CI) | Funding / price / cost | F-C interval status |
|---|---:|---:|---:|---|
| short-only-daily | -70.04% [-143.26%, -0.20%] | -2.654 [-5.625, -0.007] | +18.50% / -83.83% / -4.71% | CI excludes 0; price <= -funding |
| long-short-daily | -48.34% [-86.67%, -10.04%] | -3.350 [-5.878, -0.697] | +12.16% / -56.23% / -4.27% | CI excludes 0; price <= -funding |
| single-name-hedged | +3.19% [-15.67%, +19.17%] | 1.621 [-6.975, 15.525] | +1.39% / +2.29% / -0.48% | NULL: CI includes 0; price > -funding |

Provenance: `study3_sc_summary.parquet: strategy, net_total_return, return_ci_low, return_ci_high, return_ci_includes_zero, sharpe, sharpe_ci_low, sharpe_ci_high, funding_pnl, price_pnl, cost_pnl`. For the daily long-short and short-only strategies, negative short-leg price loss divides approximately 40% pre-rebalance-drop / 60% forward-squeeze (`pre_drop_loss_fraction=0.399972`, `forward_squeeze_loss_fraction=0.600028`).

Key caveats: hourly candles omit sub-hour squeeze paths; 61 half-spreads are assumptions, versus 7 measured pre-cutoff L4 spreads; funding and price entry windows differ by 1–2 settlements; final open positions have no terminal-liquidation cost.

## S-D: funding clock (F-D)

F-D has `DOES NOT SEPARATE` interval geometry in all 12 headline brackets: six brackets for SKHX/SMSN full-window L4 and six for the eight-market 3.5-day candle cohort. The all-market repeat-wallet short-open/close-share difference from the +30m baseline is 0.0896 percentage points (95% CI [-0.3161, 0.4919]); SKHX is 0.1522 pp ([-0.2959, 0.5956]) and SMSN 0.0246 pp ([-0.6719, 0.7292]).

Provenance: `study3_sd_brackets.parquet: group_type=all, coverage_group, bracket_minutes, ci_low, ci_high, baseline_ci_low, baseline_ci_high, separation_status` (12/12 `DOES NOT SEPARATE`); `study3_sd_wallet_flow.parquet: market_group, metric=short_open_close_share_difference, estimate, ci_low, ci_high`.

Key caveats: SKHX/SMSN use full-window L4; the other eight markets use about 3.5 days of cached candles. Of 2,650 SKHX/SMSN L4 files found, 776 were skipped for corruption or absent `user_taker` (`study3_funding_clock_2026-07-10.md`, coverage accounting; these counts are not serialized in the designated parquets).

## S-E: cross-dex spreads (F-E)

F-E: basis p95 exceeds the persistence-horizon funding edge for 57/57 twin pairs; 40/57 never exceed taker breakeven and 14/57 never exceed maker breakeven. The basis comparison is scale-invariant because both basis excursion and horizon return use the same log-price scale. The XMR pair `flx:XMR|hyna:XMR` has mean absolute funding-difference APR 144.85% (95% CI [121.07%, 173.22%]), half-life 0.67h ([0.40h, 1.31h]), and time above breakeven of 4.44% maker / 1.39% taker; the source report carries the near-dead-hyna venue-quality flag.

Provenance: `study3_se_spreads.parquet: pair_id` (57 rows), `taker_never_exceeds_breakeven=true` (40), `maker_never_exceeds_breakeven=true` (14), and `basis_p95_abs_excursion > p95_diff_horizon_return` (57); XMR columns `mean_abs_diff_apr, mean_abs_diff_apr_ci_low, mean_abs_diff_apr_ci_high, persistence_half_life_hours, persistence_half_life_hours_ci_low, persistence_half_life_hours_ci_high, pct_time_gt_maker_breakeven, pct_time_gt_taker_breakeven`.

Key caveats: exact underlier mappings are audited but do not remove venue-quality differences; half-spreads without exact pre-2026-06-18 L4 coverage use the stated 2× measured-median assumption; poisoned post-2026-06-18 quotes are excluded.

## S-F: funding and forced-flow timing (F-F)

The pooled high/low funding-bucket event-rate ratio is 0.8417; the source report's per-market intervals are SKHX [0.6895, 1.0182] and SMSN [0.6659, 1.0510], each containing 1. F-F status: per-market rate-ratio intervals include 1; the pooled difference is market-selection geometry rather than within-market timing geometry. Pooled event rates are 1.157348 events/market-hour (95% CI [1.034886, 1.278416]) at APR >=100% and 1.374975 ([1.234289, 1.521479]) at APR <0%. The high-APR BUY wallet-minus-control value is 0.0000 in the source report. The 24h hazard window is saturated (probabilities 0.9176–0.9775 across pooled funding buckets); the added 2h window spans 0.6883–0.7525.

Provenance: `study3_sf_event_rates.parquet: analysis_cut=apr_bucket, funding_bucket, event_rate_per_market_hour, ci_low, ci_high` (pooled ratio recomputed as 1.157348/1.374975); `study3_sf_hazard.parquet: scope=ALL, hazard_horizon_hours, probability_event_within_horizon, coverage_saturated`. The per-market rate-ratio intervals and wallet bridge are report-level cells in `study3_funding_forced_flow_2026-07-10.md`; the designated event-rate parquet does not serialize per-market ratios or wallet columns.

Key caveats: only SKHX/SMSN are covered; all 2,573 events are proxy-tagged repeated-taker bursts, not confirmed liquidations; the 24h hazard is coverage-saturated.

## Cross-study numeric synthesis

Observed mean APR reaches 203.21% [123.42%, 284.18%]. The 24h persistence bar has 0/183 passing observations, with half-life median 1.30h and maximum 9.93h. Daily short-only and long-short net returns are -70.04% [-143.26%, -0.20%] and -48.34% [-86.67%, -10.04%]; the hedged return is +3.19% [-15.67%, +19.17%]. F-D headline interval geometry is `DOES NOT SEPARATE` in 12/12 brackets. F-E basis geometry exceeds the funding edge in 57/57 pairs. F-F per-market rate-ratio intervals include 1.

Sources: the column-level provenance in S-A through S-F above.

## Open Follow-ups

1. **Markets gap:** CoinAPI flat-file discovery contained no `mkts` objects; vendor coverage versus naming remains unresolved. Source: `summary_studies_1_2_2026-07-09.md`.
2. **Oracle inception:** the first observed partition is 2026-06-17 16:00 UTC; actual feed inception remains unverified. Sources: `summary_studies_1_2_2026-07-09.md`; `study3_mechanics_2026-07-10.md`.
3. **SKU billing:** decimal GB versus GiB and actual HL Oracle Prices / HL System Events SKU rates remain externally unreconciled. Sources: `summary_studies_1_2_2026-07-09.md`; `spend_accounting_2026-07-09.md`.
4. **T6-1 exception handling:** corrupt-gzip and missing-`user_taker` skips still depend on brittle exception-message substrings. Source: `summary_studies_1_2_2026-07-09.md`.
5. **T7 residuals and poisoned quotes:** PENDING/REJECTED depth semantics, atomic part writes, duplicate-key ordinal synchronization, and permanent exclusion of post-2026-06-18 poisoned depth remain carried items. Source: `summary_studies_1_2_2026-07-09.md`.
6. **Auto-recharge:** enabled CoinAPI auto-recharge failed and remains an operational support item before another paid pull. Source: `summary_studies_1_2_2026-07-09.md`.
7. **Study-1 L4 cross-check:** the optional L4-quotes-as-L1 markout remains deferred, with its queue model to be labeled top-of-book/coarser. Source: `study1_offhours_markout_2026-07-09.md`.
8. **S-A persistence override:** the 24h half-life bar remains a documented operator override point; this report leaves it unchanged. Source: `study3_funding_census_2026-07-10.md`.
9. **S-B per-dex oracle attribution:** SP500 remains excluded because bare oracle identifiers collide across dexes and no contemporaneous per-dex historical oracle labeling is on disk. Source: `study3_mechanics_2026-07-10.md`.
10. **S-B absolute calibration:** the approximately 13% affine identity gap remains unresolved for absolute funding-level use. Source: `study3_mechanics_2026-07-10.md`.
11. **S-C/S-E spread coverage:** 61 S-C markets and S-E markets without exact book coverage retain the explicit 2× measured-median half-spread assumption. Sources: `study3_carry_backtest_2026-07-10.md`; `study3_cross_dex_spreads_2026-07-10.md`.
12. **S-C execution timing:** the 1–2-settlement funding/price-entry asymmetry and omitted terminal-liquidation cost remain documented implementation gaps. Source: `study3_carry_backtest_2026-07-10.md`.
13. **S-C intra-hour tails:** hourly candles still cannot observe the linked Study-2 sub-hour squeeze excursions. Source: `study3_carry_backtest_2026-07-10.md`.
14. **S-D breadth and ingestion:** eight markets remain limited to about 3.5 days, and SKHX/SMSN repeat-wallet input retains corruption/missing-`user_taker` skips. Source: `study3_funding_clock_2026-07-10.md`.
15. **S-E XMR/hyna venue flag:** the top funding-differential pair remains tagged as a near-dead-hyna venue-quality/erratic-funding artifact. Source: `study3_cross_dex_spreads_2026-07-10.md`.
16. **S-F event coverage:** confirmed liquidation/ADL/forced-close data and venue-wide coverage remain absent; SKHX/SMSN proxy tags are the only linkage inputs. Sources: `study3_funding_forced_flow_2026-07-10.md`; `study2_forced_flow_2026-07-09.md`.
17. **S-F hazard horizon:** the pre-registered 24h window remains saturated; the reported 2h view is the added discriminating horizon. Source: `study3_funding_forced_flow_2026-07-10.md`.

