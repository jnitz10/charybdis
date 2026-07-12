# Study 3 S-C-bis: long side of the funding sort

Research-only measurement from on-disk T1/T2 inputs; harness, costs, universe, schedule, and bootstrap identical to S-C (`run_study3_carry`). Long strategies pay funding and full entry/turnover costs. No out-of-sample window exists: the on-disk history (2026-01-01 to 2026-07-10) is the full S-C window, so all splits below are in-sample partitions.

| Strategy | Net total return (95% CI) | Sharpe (95% CI) | Funding | Price | Cost | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| long-top-daily | 60.615% [-8.999%, 134.222%] | 2.297 [-0.344, 5.266] | -18.499% | 83.826% | -4.712% | -24.710% |
| long-top-8h | 25.552% [-44.206%, 92.960%] | 1.035 [-1.817, 3.799] | -19.778% | 53.461% | -8.131% | -27.260% |
| long-universe-daily | 16.281% [-26.085%, 60.050%] | 1.062 [-1.697, 4.097] | -4.821% | 21.473% | -0.371% | -16.427% |

## Selection alpha (long-top-daily minus long-universe-daily, paired by rebalance)

Net alpha 44.334% (95% CI [-4.464%, 96.019%]); decomposition: funding -13.677%, price 62.353%, cost -4.341%. Period-net correlation between the two strategies: 0.738.

## Monthly net PnL

| Month | long-top-daily | long-universe-daily |
|---|---:|---:|
| 2026-01 | 21.079% | -0.882% |
| 2026-02 | -11.236% | -5.215% |
| 2026-03 | -7.798% | -3.564% |
| 2026-04 | 29.525% | 16.978% |
| 2026-05 | 35.107% | 15.591% |
| 2026-06 | 3.361% | -3.031% |
| 2026-07 | -9.422% | -3.597% |

## Regime conditioning (long-top-daily)

| Split | Periods | Net PnL | Alpha vs universe |
|---|---:|---:|---:|
| down_tape | 70 | 4.113% | 5.377% |
| up_tape | 112 | 56.502% | 38.957% |
| down_period | 80 | -92.883% | 0.910% |
| up_period | 102 | 153.499% | 43.425% |
| H1 | 91 | 16.955% | 19.235% |
| H2 | 91 | 43.661% | 25.099% |

Trailing regime uses the equal-weight universe close-to-close return over the seven days known at rebalance (sign split). Concurrent regime uses the same-period long-universe price PnL sign and is descriptive only (not tradeable).

## Where the long gains came from (mirror of the S-C reverse-causation split)

| Gain path | Long price gains |
|---|---:|
| bounce_after_drop | 220.389% |
| continued_squeeze | 330.622% |

`bounce_after_drop` gains come from names whose trailing seven-day return was negative at entry (S-C interpretation B, reverse causation); `continued_squeeze` gains come from names still rising at entry (interpretation A, funding as squeeze compensation).

## Provenance

Inputs: `study3_universe.parquet`, `study3_funding_all.parquet`, `study3_candles_1h.parquet`, `study3_fee_table.parquet`, spread table reconstructed from `study3_sc_backtest.parquet` (7 measured markets, uniform assumed value elsewhere). Output: `study3_scbis_backtest.parquet`. No network calls or paid data; terminal open positions incur no liquidation cost (same convention as S-C).

## Gate variant (post-hoc, added same day)

Causal gate: hold only when the trailing seven-day equal-weight universe return known at rebalance is non-negative (risk-on 112/182 rebalances, 25 flips; flip turnover is charged).

| Strategy | Net total return (95% CI) | Sharpe (95% CI) | Funding | Price | Cost | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| long-top-daily-gated | 55.083% [4.480%, 108.323%] | 3.537 [0.311, 6.770] | -13.076% | 72.339% | -4.180% | -23.087% |
| long-universe-daily-gated | 16.232% [-8.893%, 42.074%] | 2.136 [-1.187, 5.517] | -3.346% | 21.101% | -1.523% | -10.974% |

Gated selection alpha (top minus universe, paired): 38.851% CI [0.841%, 76.517%].

Monthly (gated top): Jan +22.447%, Feb −5.749%, Mar −14.740%, Apr +26.096%, May +31.222%, Jun +2.669%, Jul −6.863%.

Named caveat — this gate was chosen after inspecting the S-C-bis regime split on the same window; the CIs above are raw 95% intervals with no adjustment for that adaptive selection, and both lower bounds sit within a few points of zero. Output: `study3_scbis_gated_backtest.parquet`.
