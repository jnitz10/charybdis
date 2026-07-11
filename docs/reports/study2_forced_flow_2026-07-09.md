# Study 2: forced-flow anatomy measurements (proxy-tagged)

Run date: 2026-07-10. Event-time range in the event artifact: 2026-05-27 17:32:24.035 through 2026-07-08 08:31:00.058. Results below are measurements and interval-comparison statuses only.

## G2 finding and proxy status

**HLSYSTEMEVENTS contains no liquidation, ADL, or forced-close record: 0 of 1,070,342 audited rows. Accordingly, none of the events in this report is a confirmed real liquidation. Every event and downstream output is `proxy-tagged` by the pre-registered fallback heuristic.** The G2 row census is recorded in `LEDGER.md`; it is not duplicated in a regenerated report parquet or JSON. The downstream classification is independently visible in `forced_flow_events_proxy.parquet` columns `trigger_source` (`proxy`) and `tag_label` (`proxy-tagged`) and in `forced_flow_analysis_meta_proxy.json` field `tag_label`.

The event artifact contains 1,367 SKHX events and 1,206 SMSN events, or 2,573 total. The proxy requires an aggressor burst at least 3 times its trailing one-hour median trade rate, price displacement at least 3 times trailing one-hour return sigma, and a repeated taker wallet. The realized minima in `rate_multiple` are 3.000 for both markets; the realized minima in `displacement_multiple` are 3.003 for SKHX and 3.000 for SMSN; every tagged row has at least one wallet. The heuristic is defined in Method and limitations below.

Source: `forced_flow_events_proxy.parquet` columns `market`, `start_time`, `rate_multiple`, `displacement_multiple`, `wallets`, `trigger_source`, and `tag_label`.

## Method and run census

Matched baselines use the same market and exact UTC clock time and duration on the nearest eligible calendar day, with earlier dates winning ties; neither an event within plus or minus 30 minutes nor a previously used baseline is allowed. The fill rule and 1s, 5s, 30s, 2m, and 10m horizons match Study 1. Markouts are in bps of notional, net of the `maker_fee_bps` and `funding_drift_*_bps` fields.

The fills artifact contains 187,895 rows: 134,223 forced-flow and 53,672 baseline. It contains 159 matched pair IDs in each arm: 90 SKHX pairs and 69 SMSN pairs, with identical pair-ID intersections within each market. The fee field is 1.5 bps on every fill. Horizon-specific `n` below excludes null/stale markouts. Intervals are nonparametric cluster-bootstrap 95% intervals over market by UTC six-hour `cluster_key`; `G` is the distinct cluster count.

Sources: `forced_flow_vs_baseline_fills_proxy.parquet` columns `market`, `window_type`, `pair_id`, `maker_fee_bps`, `cluster_key`, `net_markout_*_bps`, `stale_*`, and `funding_drift_*_bps`; matching rule from `data/study2_t7_plan.json` field `baseline_matching_rule`.

## Primary decision number: net markouts by horizon

Each forced-flow and baseline cell is `point estimate (n, G; 95% CI)`. “Overlap” reports the numeric intersection of the two intervals and its width. “Separated” reports the open gap between the nearest endpoints and which interval is above the other. These statuses describe interval geometry only.

| Market | Horizon | Forced-flow net bps | Baseline net bps | Interval-comparison status |
|---|---|---:|---:|---|
| SKHX | 1s | -0.055 (n=98212, G=62; 95% CI [-0.503, 0.414]) | 0.038 (n=43540, G=73; 95% CI [-0.541, 0.598]) | overlap [-0.503, 0.414], width 0.917 bps |
| SKHX | 5s | -0.903 (n=98212, G=62; 95% CI [-1.348, -0.462]) | -0.924 (n=43540, G=73; 95% CI [-1.539, -0.386]) | overlap [-1.348, -0.462], width 0.886 bps |
| SKHX | 30s | -1.481 (n=98212, G=62; 95% CI [-2.054, -0.949]) | -1.602 (n=43540, G=73; 95% CI [-2.387, -0.991]) | overlap [-2.054, -0.991], width 1.063 bps |
| SKHX | 2m | -1.266 (n=98018, G=62; 95% CI [-1.911, -0.633]) | -2.027 (n=43431, G=73; 95% CI [-3.291, -0.961]) | overlap [-1.911, -0.961], width 0.950 bps |
| SKHX | 10m | -0.829 (n=97139, G=62; 95% CI [-3.074, 1.517]) | -1.973 (n=43065, G=72; 95% CI [-3.840, -0.438]) | overlap [-3.074, -0.438], width 2.636 bps |
| SMSN | 1s | 0.566 (n=35999, G=58; 95% CI [0.058, 1.112]) | 2.670 (n=9979, G=59; 95% CI [1.147, 4.539]) | separated by 0.035 bps; baseline interval above forced-flow |
| SMSN | 5s | -0.590 (n=35999, G=58; 95% CI [-1.118, -0.033]) | 0.605 (n=9979, G=59; 95% CI [-1.716, 2.919]) | overlap [-1.118, -0.033], width 1.084 bps |
| SMSN | 30s | -1.773 (n=35999, G=58; 95% CI [-2.434, -1.153]) | -2.599 (n=9979, G=59; 95% CI [-8.020, 1.195]) | overlap [-2.434, -1.153], width 1.282 bps |
| SMSN | 2m | -2.009 (n=35923, G=58; 95% CI [-2.655, -1.381]) | -5.266 (n=9905, G=59; 95% CI [-15.004, 0.602]) | overlap [-2.655, -1.381], width 1.274 bps |
| SMSN | 10m | -2.065 (n=35579, G=57; 95% CI [-3.066, -0.988]) | -2.971 (n=9812, G=59; 95% CI [-8.592, 1.119]) | overlap [-3.066, -0.988], width 2.079 bps |
| Pooled | 1s | 0.111 (n=134211, G=120; 95% CI [-0.211, 0.512]) | 0.529 (n=53519, G=132; 95% CI [-0.016, 1.221]) | overlap [-0.016, 0.512], width 0.528 bps |
| Pooled | 5s | -0.819 (n=134211, G=120; 95% CI [-1.151, -0.453]) | -0.639 (n=53519, G=132; 95% CI [-1.303, 0.041]) | overlap [-1.151, -0.453], width 0.697 bps |
| Pooled | 30s | -1.560 (n=134211, G=120; 95% CI [-2.010, -1.134]) | -1.788 (n=53519, G=132; 95% CI [-3.114, -0.853]) | overlap [-2.010, -1.134], width 0.876 bps |
| Pooled | 2m | -1.465 (n=133941, G=120; 95% CI [-1.975, -0.971]) | -2.628 (n=53336, G=132; 95% CI [-4.966, -1.019]) | overlap [-1.975, -1.019], width 0.955 bps |
| Pooled | 10m | -1.160 (n=132718, G=119; 95% CI [-2.795, 0.603]) | -2.158 (n=52877, G=131; 95% CI [-4.102, -0.644]) | overlap [-2.795, -0.644], width 2.151 bps |

Source: direct cells in `forced_flow_vs_baseline_markout_proxy.parquet` columns `market`, `window_type`, `horizon`, `point_estimate_bps`, `ci_low_bps`, `ci_high_bps`, `n`, and `G`. Interval intersections and gaps use only the displayed CI endpoints.

## Coverage and differential attenuation

**The usable quote era is 2026-05-08 through 2026-06-18 only. After June 18, CoinAPI `ask_px` is frozen, a confirmed feed artifact rather than an executable market state.** The coverage evidence is that all 1,714,803 observed quote rows in the 410 post-June-18 windows are crossed, while 3,997,356 contemporaneous trade rows continue and none of those windows produces fills. The metadata therefore records 2026-06-18 as the last usable quote date.

Across both arms, 434 of 1,100 windows, or 39.5%, are dropped for crossed quotes. Differential attenuation is substantial: forced-flow windows have a 57.8% mean crossed-row fraction versus 27.3% for baselines, a difference of +30.4 percentage points. The corresponding medians are 100.0% and 0.0%. At the window level, 317 of 579 forced-flow windows (54.7%) and 117 of 521 baseline windows (22.5%) are dropped for crossed quotes.

| Arm | Windows | Dropped for crossed quotes | Dropped fraction | Mean crossed-row fraction | Median crossed-row fraction |
|---|---:|---:|---:|---:|---:|
| Forced-flow | 579 | 317 | 54.7% | 57.8% | 100.0% |
| Baseline | 521 | 117 | 22.5% | 27.3% | 0.0% |
| Combined | 1,100 | 434 | 39.5% | not computed | not computed |

This differential selection biases the forced-flow arm toward the calmer subset that survives quote sanitation. Consequently, the forced-flow/baseline markout comparison is confounded and conservative with respect to more dislocated forced-flow moments. This is a documented limitation of the comparison, not a directional interpretation of the measured markouts.

Sources: `forced_flow_quote_coverage_proxy.parquet` columns `window_type`, `window_start`, `quote_rows`, `crossed_quote_rows`, `crossed_row_fraction`, `dropped_for_crossed_quotes`, `trade_rows`, and `produced_fills`; `forced_flow_analysis_meta_proxy.json` fields under `quote_coverage`; duplicated coverage columns in `forced_flow_vs_baseline_markout_proxy.parquet`.

## Cascade anatomy

The anatomy artifact has 2,573 event rows. Anatomy is computed for 1,312 events (682 SKHX and 630 SMSN); the other 1,261 rows are labeled `unavailable executable-quote/depth coverage`. Overshoot is non-null for 1,080 computed events. Reversion half-life is non-null for 971: 96 computed events are right-censored because half reversion is not observed, and 13 have zero overshoot. A further 232 computed rows have no overshoot value. Anatomy confidence intervals were not computed in the regenerated outputs.

Post-June-18 anatomy is **coverage absent and untrustworthy regardless of any other caveat**. The post-cut book contains never-deleted phantom limits; depth and executable-quote anatomy from that era must not be used.

### Overshoot and reversion half-life

| Market | Overshoot n | Mean overshoot bps | Median overshoot bps | Overshoot p90 bps | Reversion n | Mean half-life s | Median half-life s | Half-life p90 s | Censored | Zero overshoot |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SKHX | 593 | 63.055 | 44.842 | 130.115 | 532 | 121.804 | 13.971 | 376.809 | 52 | 9 |
| SMSN | 487 | 55.444 | 37.951 | 114.752 | 439 | 110.689 | 16.146 | 329.990 | 44 | 4 |
| Pooled | 1,080 | 59.623 | 42.190 | 123.225 | 971 | 116.779 | 14.900 | 368.323 | 96 | 13 |

### Depth consumed and duration

| Market | Computed n | Mean levels consumed | Median levels consumed | Mean size consumed | Median size consumed | Mean duration s | Median duration s | Mean size shortfall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| SKHX | 682 | 29.022 | 19 | 131.836 | 41.513 | 56.523 | 54.541 | 0.000 |
| SMSN | 630 | 19.030 | 14 | 223.833 | 101.895 | 49.215 | 47.606 | 0.000 |
| Pooled | 1,312 | 24.224 | 17 | 176.011 | 67.730 | 53.014 | 51.995 | 0.000 |

Sources: `forced_flow_event_anatomy_proxy.parquet` columns `market`, `anatomy_covered`, `anatomy_coverage`, `overshoot_bps`, `reversion_half_life_seconds`, `reversion_censored`, `zero_overshoot`, `depth_levels_consumed`, `depth_size_consumed`, `depth_size_shortfall`, and `duration_seconds`; `forced_flow_analysis_meta_proxy.json` fields `anatomy_rows`, `anatomy_computed_rows`, `anatomy_errors`, and `reversion`.

## Conditioning

### Funding state

Funding state is the trailing 24-hour mean APR bucket. Event `n` is the complete proxy-event count in each bucket. Metric-specific non-null `n` and confidence intervals are not computed in this summary artifact.

| Market | Funding APR bucket | Event n | Mean overshoot bps | Mean half-life s | Censored | Zero overshoot | Mean depth levels consumed |
|---|---|---:|---:|---:|---:|---:|---:|
| SKHX | negative | 149 | 66.132 | 160.661 | 5 | 0 | 31.781 |
| SKHX | 0%-25% | 330 | 67.732 | 162.691 | 12 | 0 | 29.149 |
| SKHX | 25%-100% | 452 | 59.218 | 91.186 | 15 | 2 | 24.140 |
| SKHX | >=100% | 436 | 62.846 | 111.574 | 20 | 7 | 33.104 |
| SMSN | negative | 274 | 56.916 | 105.365 | 11 | 0 | 19.572 |
| SMSN | 0%-25% | 212 | 60.998 | 104.840 | 6 | 0 | 18.724 |
| SMSN | 25%-100% | 449 | 57.939 | 131.531 | 17 | 4 | 19.693 |
| SMSN | >=100% | 271 | 46.972 | 86.099 | 10 | 0 | 17.435 |

Source: direct cells in `forced_flow_conditioning_funding_proxy.parquet` columns `market`, `funding_state`, `event_n`, `mean_overshoot_bps`, `mean_reversion_half_life_seconds`, `censored_count`, `zero_overshoot_count`, and `mean_depth_levels_consumed`.

### Open interest

Historical OI is absent from the supplied inputs, so no current-OI value and no look-ahead substitution are used. The explicit null census contains 81 market-date rows: 41 SKHX and 40 SMSN, spanning 2026-05-27 through 2026-07-08. Every row has `available=false` and null `open_interest`; therefore OI-conditioned anatomy is not computed.

Source: `forced_flow_conditioning_oi_daily_proxy.parquet` columns `market`, `date`, `open_interest`, `available`, and `source`; `forced_flow_analysis_meta_proxy.json` field `oi_limitation`.

### Oracle update class crossed with KRX state

“Fallback-present” means at least one Fallback update is observed around an event; “deployer-only” means observed oracle updates are all Deployer; “unavailable” means no qualifying oracle observations. Blank output means the requested mean is not computed.

| Market | KRX state | Oracle regime | Event n | Mean fallback frequency | Mean overshoot bps | Mean half-life s | Censored | Zero overshoot |
|---|---|---|---:|---:|---:|---:|---:|---:|
| SKHX | frozen | deployer-only | 638 | 0.000000 | 74.460 | 161.926 | 1 | 0 |
| SKHX | frozen | fallback-present | 8 | 0.005889 | not computed | not computed | 0 | 0 |
| SKHX | frozen | unavailable | 528 | not computed | 60.851 | 125.193 | 43 | 9 |
| SKHX | live | deployer-only | 86 | 0.000000 | 181.845 | not computed | 1 | 0 |
| SKHX | live | unavailable | 107 | not computed | 72.938 | 99.312 | 7 | 0 |
| SMSN | frozen | deployer-only | 525 | 0.000000 | 36.726 | 46.459 | 2 | 0 |
| SMSN | frozen | fallback-present | 1 | 0.007860 | not computed | not computed | 0 | 0 |
| SMSN | frozen | unavailable | 455 | not computed | 52.926 | 103.785 | 32 | 3 |
| SMSN | live | deployer-only | 113 | 0.000000 | 43.807 | 166.211 | 1 | 0 |
| SMSN | live | unavailable | 112 | not computed | 68.191 | 135.041 | 9 | 1 |

Source: direct cells in `forced_flow_conditioning_oracle_krx_proxy.parquet` columns `market`, `krx_state`, `oracle_regime`, `event_n`, `mean_fallback_frequency`, `mean_overshoot_bps`, `mean_reversion_half_life_seconds`, `censored_count`, and `zero_overshoot_count`; event-level labels in `forced_flow_conditioning_events_proxy.parquet` columns `krx_state`, `krx_session_label`, `oracle_deployer_updates`, `oracle_fallback_updates`, `oracle_fallback_frequency`, `oracle_regime`, and `oracle_observations`.

## Biases and assumptions

- Proxy definition: fixed UTC-minute candidates require trade rate at least 3 times the trailing one-hour median, price displacement at least 3 times trailing one-hour return sigma, and a repeated `user_taker` wallet. This identifies pre-registered proxy flow, not venue-confirmed liquidation flow. When the trailing median or return sigma is zero, the detector abstains; the suppressed-candidate census is not computed in the regenerated report outputs.
- The fixed UTC-minute bucket is not a sliding 60-second window. A burst straddling a minute boundary can be split and under-detected; merging joins only buckets that already qualify.
- The simulated passive fill is an optimistic upper bound because prints do not reveal cancellations ahead, hidden liquidity, exact priority, or the simulated order's effect on later flow.
- The maker fee is assumed at 1.5 bps. Funding uses the latest known hourly value and is netted separately for each horizon.
- The quote sanitation is differentially attenuating: forced-flow mean crossed-row fraction is 57.8% and baseline is 27.3%. The comparison limitation is documented in Coverage and differential attenuation.
- Post-June-18 quote and depth anatomy is coverage absent because of the frozen-ask/crossed-book artifact and never-deleted phantom limits.
- Spend uses decimal GB (`bytes / 1,000,000,000`). CoinAPI console billing and the assumed pricing of Hyperliquid-specific SKUs remain external reconciliation items.

## Artifacts and follow-ups

- Event tags: `data/reports/forced_flow_events_proxy.parquet`.
- Anatomy: `data/reports/forced_flow_event_anatomy_proxy.parquet`.
- Markout summary and per-fill rows: `data/reports/forced_flow_vs_baseline_markout_proxy.parquet` and `data/reports/forced_flow_vs_baseline_fills_proxy.parquet`.
- Coverage: `data/reports/forced_flow_quote_coverage_proxy.parquet` and `data/reports/forced_flow_analysis_meta_proxy.json`.
- Conditioning: `data/reports/forced_flow_conditioning_events_proxy.parquet`, `data/reports/forced_flow_conditioning_funding_proxy.parquet`, `data/reports/forced_flow_conditioning_oracle_krx_proxy.parquet`, and `data/reports/forced_flow_conditioning_oi_daily_proxy.parquet`.
- The collated MED/LOW follow-up list appears in `summary_studies_1_2_2026-07-09.md`.
