# Study 3 T0: funding formula and HIP-3 fee inputs

Checked 2026-07-10. This is a source audit, not an empirical reconciliation.

## Funding mechanics doc-check

Primary source: [Hyperliquid Funding documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding) ([Markdown](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/funding.md)). The page was reachable with `curl` (HTTP 200) on 2026-07-10.

| Claim | Status | Finding |
|---|---|---|
| Settlement cadence | verified | The docs say funding is “paid every hour.” The documented formula computes an 8-hour rate and pays one eighth each hour. Funding-history timestamps remain exact settlement timestamps; they must not be backfilled. |
| Rate formula | verified | The documented formula is `Funding Rate = Average Premium Index + clamp(interest rate - Premium Index, -0.0005, 0.0005)`. This corrects the plan's shorthand: the clamp applies to interest minus premium; it is not a clamp around the entire rate. |
| Premium sampling | verified | The docs state the “premium is sampled every 5 seconds” and averaged over the hour. Core-perp premium uses impact bid/ask relative to oracle. |
| HIP-3 premium | verified | HIP-3 uses a distinct midpoint-impact formula: `0.5 * (impact_bid_px + impact_ask_px) / oracle_px - 1`, against the deployer oracle, with deployer-configurable funding multiplier and interest-rate fields. |
| Cap and interval on HIP-3 | verified | The docs state a 4%/hour funding cap and explicitly say cap and interval do not depend on the asset; this covers HIP-3. |
| Same clamp and interest on HIP-3 | assumed | The page does not explicitly say the post-multiplier HIP-3 calculation retains identical clamp behavior. It also says deployers can express behavior through funding multiplier and interest rate, so an identical fixed interest component is not valid across HIP-3 markets. Live `perpDexs` exposes `assetToFundingMultiplier` and `assetToFundingInterestRate`. T4 must reconcile these controls empirically rather than hardcode the core constants. |

## Fee table

Machine-readable source of truth: `data/reports/study3_fee_table.parquet`.

The requested base maker/taker inputs (1.5/4.5 bps) remain **assumed**; this T0 did not find a current primary fee-schedule citation establishing those values for every account tier. `deployerFeeScale` is **verified** from the public `perpDexs` response cached on 2026-07-10. Effective values follow the pre-registered calculation `base_bps * deployerFeeScale`, so they remain assumed because one factor is assumed. The parquet `source` cell records provenance separately for every numeric column.

| dex | base maker bps | base taker bps | deployer fee scale | effective maker bps | effective taker bps |
|---|---:|---:|---:|---:|---:|
| abcd | 1.5 | 4.5 | 1.0 | 1.5 | 4.5 |
| cash | 1.5 | 4.5 | 1.0 | 1.5 | 4.5 |
| flx | 1.5 | 4.5 | 1.0 | 1.5 | 4.5 |
| hyna | 1.5 | 4.5 | 0.1111 | 0.16665 | 0.49995 |
| km | 1.5 | 4.5 | 1.0 | 1.5 | 4.5 |
| mkts | 1.5 | 4.5 | 1.0 | 1.5 | 4.5 |
| para | 1.5 | 4.5 | 1.0 | 1.5 | 4.5 |
| vntl | 1.5 | 4.5 | 1.0 | 1.5 | 4.5 |
| xyz | 1.5 | 4.5 | 1.0 | 1.5 | 4.5 |

## G-F3 REST budget for T1

Use the plan's conservative 289-market universe: at most 7 funding pages for a market with SKHX-length history, plus one 1h-candle call and one 1d-candle call, gives `289 * (7 + 2) = 2,601` market calls. Add one `perpDexs` call and nine `metaAndAssetCtxs` calls: **2,611 calls**. At the allowed ceiling of 2 requests/second this is **21 minutes 46 seconds** before backoff/network overhead; at the client's conservative 1 request/second default it is **43 minutes 31 seconds**. Disk-cache hits cost zero REST calls.

Live metadata on 2026-07-10 contained 225 universe entries across the nine DEXes, below the plan's approximately 289 markets. T1 should reconcile active versus delisted markets, but the 2,611-call figure deliberately retains the larger planning universe as a capacity bound.
