# Study 3 S-C: cross-sectional carry backtest

Research-only measurement from on-disk T1/T2 inputs. Values are reported without an operator adjudication.

## Portfolio decomposition and uncertainty

Additive cross-sectional returns use gross-one portfolios (long-short is 0.5 per side). The hedged strategy uses a unit SKHX short plus its trailing-beta hedge basket, so its gross exposure varies with beta and is not normalized to gross one. Immediate scheduled rebalances use effective taker fees from `study3_fee_table.parquet`; initial entries and every transition are charged, while no unscheduled terminal liquidation is added. Intervals use a 2,000-draw, seed-0, 95% bootstrap of scalar portfolio holding-period returns after all markets, legs, and UTC-six-hour sub-blocks are netted within each rebalance period; resampling therefore preserves same-period cross-market dependence.

| Strategy | Net total return (95% CI) | Sharpe (95% CI) | Funding | Price | Cost | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| long-short-8h | -29.539% [-64.945%, 6.213%] | -2.222 [-4.867, 0.451] | 13.015% | -35.541% | -7.013% | -30.804% |
| long-short-daily | -48.339% [-86.668%, -10.035%] | -3.350 [-5.878, -0.697] | 12.162% | -56.231% | -4.269% | -50.417% |
| short-only-8h | -41.814% [-109.090%, 27.665%] | -1.695 [-4.460, 1.126] | 19.778% | -53.461% | -8.131% | -62.507% |
| short-only-daily | -70.039% [-143.262%, -0.199%] | -2.654 [-5.625, -0.007] | 18.499% | -83.826% | -4.712% | -84.989% |
| single-name-hedged | 3.193% [-15.671%, 19.166%] | 1.621 [-6.975, 15.525] | 1.386% | 2.289% | -0.482% | -5.634% |
| single-name-unhedged | -81.937% [-188.072%, 21.391%] | -2.549 [-5.874, 0.669] | 24.417% | -106.255% | -0.099% | -110.971% |

The hedged 3.193% result is price-residual dominated: funding 1.386%, price 2.289%, and cost -0.482%.

## Cumulative curves, numerical description

| Strategy | Rebalances | End | Minimum | Maximum | Worst price-PnL period (time) |
|---|---:|---:|---:|---:|---:|
| long-short-8h | 550 | -29.539% | -30.120% | 0.685% | -4.539% (2026-04-07 16:00:00) |
| long-short-daily | 182 | -48.339% | -50.417% | 0.000% | -5.136% (2026-04-07 00:00:00) |
| short-only-8h | 550 | -41.814% | -57.262% | 5.245% | -7.631% (2026-06-24 16:00:00) |
| short-only-daily | 182 | -70.039% | -84.989% | 0.000% | -8.595% (2026-02-11 00:00:00) |
| single-name-hedged | 17 | 3.193% | -5.634% | 3.193% | -5.311% (2026-07-03 00:00:00) |
| single-name-unhedged | 140 | -81.937% | -96.773% | 14.198% | -14.703% (2026-03-09 00:00:00) |

Worst individual short-leg price contributions (unoffset by other legs):

| Strategy | Market | UTC block | Price PnL |
|---|---|---:|---:|
| long-short-8h | xyz:HIMS | 2026-04-15 18:00:00 | -3.187% |
| long-short-daily | xyz:HIMS | 2026-04-15 18:00:00 | -3.205% |
| short-only-8h | xyz:HIMS | 2026-04-15 18:00:00 | -6.374% |
| short-only-daily | xyz:HIMS | 2026-04-15 18:00:00 | -6.409% |
| single-name-hedged | xyz:SKHX | 2026-06-24 18:00:00 | -12.600% |
| single-name-unhedged | xyz:SKHX | 2026-06-24 18:00:00 | -12.600% |

## Falsification F-C numbers

| Strategy | Return CI includes 0 | Price PnL | −Funding PnL | Price <= −Funding |
|---|:---:|---:|---:|:---:|
| long-short-8h | True | -35.541% | -13.015% | True |
| long-short-daily | False | -56.231% | -12.162% | True |
| short-only-8h | True | -53.461% | -19.778% | True |
| short-only-daily | False | -83.826% | -18.499% | True |
| single-name-hedged | True | 2.289% | -1.386% | False |
| single-name-unhedged | True | -106.255% | -24.417% | True |

## Reverse-causation diagnostic

Negative short-leg price PnL is split by the name's close-to-close return over the seven days known at rebalance. `pre_rebalance_drop` means that return was negative; `forward_squeeze` means it was non-negative. Fractions use classified loss only; unknown-history loss is shown separately.

| Strategy | Pre-drop loss | Forward-squeeze loss | Pre-drop fraction | Forward-squeeze fraction | Unknown-history loss |
|---|---:|---:|---:|---:|---:|
| long-short-8h | 107.153% | 156.337% | 40.667% | 59.333% | 0.000% |
| long-short-daily | 110.194% | 165.311% | 39.997% | 60.003% | 0.000% |
| short-only-8h | 214.306% | 312.673% | 40.667% | 59.333% | 0.000% |
| short-only-daily | 220.389% | 330.622% | 39.997% | 60.003% | 0.000% |
| single-name-hedged | 46.341% | 22.208% | 67.602% | 32.398% | 0.000% |
| single-name-unhedged | 204.691% | 350.359% | 36.878% | 63.122% | 3.968% |

Interpretation A is that funding compensates forward squeeze risk; its diagnostic bucket is `forward_squeeze`. Interpretation B is reverse causation: the trailing funding signal selects names that had already fallen and subsequently recovered; its diagnostic bucket is `pre_rebalance_drop`. No verdict is rendered between these interpretations.

The pre-registered +340% APR prior is retained as a prior only; the split above prevents treating the aggregate loss as evidence that the market prices funding correctly.

## Cost sensitivity and spread provenance

| Strategy | All eligible markets | Measured-spread markets only |
|---|---:|---:|
| long-short-8h | -29.539% | 9.634% |
| long-short-daily | -48.339% | -11.990% |
| short-only-8h | -41.814% | -24.070% |
| short-only-daily | -70.039% | -68.207% |
| single-name-hedged | 3.193% | 3.193% |
| single-name-unhedged | -81.937% | -81.937% |

Measured pre-cutoff L4 half-spreads (7): xyz:EWY, xyz:KR200, xyz:SKHX, xyz:SMH, xyz:SMSN, xyz:SP500, xyz:XYZ100.

Assumed half-spreads (61), each explicitly set to 2× the median of the eight Study-1 markets' pre-cutoff hourly-segment median spreads: mkts:US500, mkts:USTECH, xyz:AAPL, xyz:AMAT, xyz:AMD, xyz:AMZN, xyz:ARM, xyz:AVGO, xyz:BABA, xyz:BB, xyz:BE, xyz:BRENTOIL, xyz:CBRS, xyz:CL, xyz:COIN, xyz:COPPER, xyz:CRCL, xyz:CRWV, xyz:DELL, xyz:DRAM, xyz:EUR, xyz:GOLD, xyz:GOOGL, xyz:HIMS, xyz:HOOD, xyz:HYUNDAI, xyz:INTC, xyz:JP225, xyz:JPY, xyz:KIOXIA, xyz:LITE, xyz:LLY, xyz:META, xyz:MINIMAX, xyz:MRVL, xyz:MSFT, xyz:MSTR, xyz:MU, xyz:NATGAS, xyz:NBIS, xyz:NFLX, xyz:NOK, xyz:NVDA, xyz:ORCL, xyz:PLTR, xyz:PURRDAT, xyz:QCOM, xyz:QNT, xyz:RIVN, xyz:RKLB, xyz:SHAZ, xyz:SILVER, xyz:SKHY, xyz:SNDK, xyz:SPCX, xyz:STRC, xyz:TSLA, xyz:TSM, xyz:WDC, xyz:XLE, xyz:ZHIPU.

## Coverage and timing

The frozen filter is `passes_liquidity_floor == true` ($1,000,000/day) plus coverage status in ['candle_truncated', 'complete', 'funding_truncated']; it selects 67 markets and ignores `carry_relevant`. Coverage counts: complete=67.
Market-days lost specifically to candle truncation: 0.000. No stale close is forward-filled. Signals use raw settlements in (t−7d,t], requiring 168 observations; funding PnL uses settlements in (t,end]. Returns use actual close timestamps from candles whose opens are strictly after rebalance, excluding the candle at/containing rebalance. This creates a small 1–2-settlement asymmetry between the funding window and the later price entry. The final open positions incur no terminal-liquidation cost. Both mechanics leave reported net returns slightly higher than an exactly aligned, fully liquidated implementation. Hedge beta is an intercept OLS slope on synchronized hourly log returns in the trailing 30 days known by rebalance, with at least 168 observations; hedged and unhedged variants rebalance daily.

| Strategy | Markets entered | Market-days entered | Market-days lost to truncation |
|---|---:|---:|---:|
| long-short-8h | 60 | 1558.667 | 0.000 |
| long-short-daily | 60 | 1542.000 | 0.000 |
| short-only-8h | 43 | 779.333 | 0.000 |
| short-only-daily | 43 | 771.000 | 0.000 |
| single-name-hedged | 4 | 68.000 | 0.000 |
| single-name-unhedged | 1 | 140.000 | 0.000 |

## Worst-squeeze intra-hour tail and named limitation

Study-2 BUY-event anatomy for SKHX: n=270, p95 overshoot=163.274 bps, maximum=339.420 bps.
Study-2 BUY-event anatomy for SMSN: n=207, p95 overshoot=144.400 bps, maximum=392.229 bps.

Named limitation — candles miss sub-hour excursions: the hourly backtest cannot observe these intra-hour squeeze paths, so the Study-2 overshoot anatomy is linked explicitly rather than folded into hourly PnL.

## Provenance

Inputs: `study3_universe.parquet`, projected `study3_funding_all.parquet` settlement columns, projected `study3_candles_1h.parquet` close columns, `study3_fee_table.parquet`, pre-2026-06-18 L4 quote books, and `forced_flow_event_anatomy_proxy.parquet`. Outputs: `study3_sc_backtest.parquet` and `study3_sc_summary.parquet`. No network calls, orders, wallets, keys, or paid data were used; cumulative spend remains $116.92.
