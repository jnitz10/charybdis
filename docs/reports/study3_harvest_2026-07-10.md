# Study 3 T1 funding harvest — 2026-07-10

## Scope and method

Research-only collection used public Hyperliquid info REST exclusively through `charybdis.hl_rest.HyperliquidInfo`. No orders, wallets, keys, or paid endpoints were used. Funding and candles begin at the T0 client's validated 2026-01-01 lower bound. Interior reconciliation still spans each series' first through last observation, but endpoint coverage is now audited separately against funding and the fixed harvest end.

## Universe reconciliation

| DEX | Current listed markets |
|---|---:|
| abcd | 1 |
| cash | 17 |
| flx | 16 |
| hyna | 25 |
| km | 23 |
| mkts | 23 |
| para | 5 |
| vntl | 15 |
| xyz | 100 |
| **Total** | **225** |

The live snapshot contained 225 currently listed HIP-3 markets, matching T0's 225-entry observation and falling 64 below the plan's rough ~289 estimate. The REST metadata snapshot only enumerates live listings; delisted markets cannot be recovered by name from that snapshot, so they are not reachable for a name-driven census.

Expected Study-1/2 market check: 13/13 present. None missing.
Verified present: `xyz:SP500`, `km:US500`, `flx:USA500`, `cash:USA500`, `km:USTECH`, `xyz:XYZ100`, `flx:USA100`, `km:SMALL2000`, `xyz:SKHX`, `xyz:SMSN`, `xyz:SMH`, `xyz:KR200`, `xyz:EWY`.

Main-dex hedge references: **BTC, ETH, SOL**. BTC and ETH were explicitly required baseline hedges; SOL was the sole additional small-list twin because SOL is listed both on the main dex and in the HIP-3 universe, making it a useful large-cap control for S-A.

## Harvest totals

Markets covered: **228** (225 HIP-3 + 3 main-dex references). Funding rows: **586,113**. 1h candle rows: **548,869**. 1d candle rows: **22,995**. Snapshot rows: **228**.

## Endpoint coverage

Of **228** total markets, **183** are data-bearing and **45** are `no_data`. Among data-bearing markets, **105** are `complete`, **78** are `candle_truncated`, and **0** are `funding_truncated` under a **2-hour** endpoint tolerance.

The adversarial review's 66 count described long candle shortfalls: this recomputation confirms **66** candle-truncated markets more than 24 hours behind funding. The strict 2-hour rule additionally captures shorter material shortfalls and **1** data-bearing market with no 1h rows, yielding the larger honest bucket above.

`gap_audit_clean` is true only for `complete` markets with no detected interior gaps. It is false for `no_data`, `candle_truncated`, and `funding_truncated` markets.

## Interior contiguity

Separately from endpoint coverage, **183/183 data-bearing markets** have no detected funding or 1h-candle gaps within their own observed spans; **0** have recorded interior gaps. Empty markets are excluded from this statement. Row-count reconciliation uses an inclusive regular grid with a one-row endpoint tolerance.

No funding or 1h candle interior gaps were found.

## STEP 0 direct probe verdict

**Real market inactivity, not a candle-pagination bug.** Direct `candle_snapshot` requests strictly after each stored last 1h candle through the fixed harvest end returned no rows:

- `km:US500`: start `1781704800000`, end `1783717197078`, returned rows **0**.
- `km:RTX`: start `1781082000000`, end `1783717197078`, returned rows **0**.
- `vntl:OPENAI`: start `1781535600000`, end `1783717197078`, returned rows **0**.

The existing candle parquets are therefore complete representations of candles returned by Hyperliquid for those windows; no candle re-fetch or pagination change was needed.

## Downstream use

T2–T7 must use each series' persisted endpoint fields and `coverage_status` when constructing joins. The market list establishes universe membership only; it does not imply that funding or candles cover the full research window. `inception_floored: true` means the first timestamp equals the imposed 2026-01-01 lower bound and must not be interpreted as a listing date.

## REST run

Actual network REST calls: **1937**; cache hits: **19**; wall-clock time: **1945.2 seconds** (32.42 minutes). Progress was logged to `data/study3_harvest.log`.

All outputs are research artifacts. `data/spend.json` remained unchanged at $116.92473877999909 (displayed as $116.92); public REST cost was $0.
