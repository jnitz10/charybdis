# Study 3 — HIP-3 Funding Deep Dive (grinder-loop handoff)

**Date:** 2026-07-10. **Operator:** jnitz. **Orchestrator:** Opus via agentic-loop skill.
**Implementer (all tasks):** GPT5.6-High via `codex:codex-rescue`. **Reviewer:** `compound-engineering:ce-adversarial-reviewer` every task; add `ce-correctness-reviewer` on T3, T4, T6 (money math).
**Ledger:** `LEDGER.md` at repo root (fresh; the completed Studies-1/2 ledger is archived at `docs/ledgers/2026-07-09-studies-1-2-LEDGER.md` — the G2 census and all prior findings live there).

## §0 Mission and budget

Deep, decision-grade characterization of HIP-3 funding rates as a source of edge. **No strategy is off the table** (operator directive 2026-07-10): carry/harvest, cross-dex funding spreads, funding-clock effects, funding-as-forced-flow-predictor, hedged single-name shorts — including vntl markets previously excluded (measure them; the "avoid" prior applies to *trading*, not *measuring*). This remains Phase-A research: measurement and backtest only, no order placement, no wallets, no keys.

**Budget:** Studies 1–2 consumed $116.92 of the $180 policy cap. Estimated CoinAPI balance ≈ **$75 (UNVERIFIED — operator should eyeball the console before T4)**. This study is deliberately cheap: every sub-study except S-B runs on free REST data or data already on disk. New flat-file spend ceiling: **$60, pause-line semantics** — same protocol as last run: at $58 projected, stop downloads, finish analyses on data in hand, write RESUME state. Single knob; operator edits this line to change it. The spend meter (`data/spend.json`, `charybdis/ffs3.py`) continues cumulatively — record Study-3 pulls under `days.<date>` as before. Auto-recharge is KNOWN BROKEN (see Studies-1/2 close-out) — a mid-pull 403 credit lockout is an expected failure mode; the T1-style resume-manifest pattern handles it.

**Run mode:** autonomous to the cap, per standing operator directive. Surface only for true blockers, plan-stale (two consecutive escalations), or the pause line.

## §1 Binding design rules (inherited — violations are BLOCKERs)

1. **No look-ahead.** Any signal used at time t must be computable from data with `time_exchange ≤ t`. Funding-specific trap: `fundingHistory` rows are *settlements* — the rate paid AT hour h was determined by the premium DURING hour h−1→h. Joins of funding to price action must use the settlement timestamp, never backfill the hour it describes.
2. **Executable prices only** where books are used. Post-2026-06-18 CoinAPI quotes are POISONED (frozen `ask_px`, permanently crossed books, phantom limits — confirmed feed artifact, see Studies-1/2). Any book-derived cost/depth number uses the 2026-05-08→06-18 window only. Trades and REST data are unaffected.
3. **Cluster-robust uncertainty.** Nonparametric cluster bootstrap, market × UTC-6h `cluster_key`, 2,000 resamples, seed 0, 95% percentile CI, min G=5 → below that, "insufficient evidence", never a numeric CI. Reuse the Study-1 implementation in `charybdis/markout.py` — do not reimplement.
4. **Memory cap:** run analysis under `systemd-run --user --scope -q -p MemoryMax=6G -p MemorySwapMax=0 uv run …`; if the user manager is unreachable (it was last run), `prlimit --as=6442450944` is the accepted fallback. Never load a full dataset when a streaming/projected scan works — `charybdis/loaders.py` patterns.
5. **REST politeness:** ≤2 req/s sustained to `api.hyperliquid.xyz`, exponential backoff on 429, cache every response to disk (`data/rest_cache/`) so re-runs are free and reproducible. Record the fetch timestamp per cached file.
6. **Null results are valid results.** Reports state numbers, CIs, and interval-geometry statuses only — **no verdicts**; the operator adjudicates against §3's pre-registered criteria.
7. **Trust the file, not the doc.** Inspect the first row of any new data source before writing a parser. Plan §2 facts marked `verified` were probed on 2026-07-10; facts marked `assumed` must be verified by the task that first depends on them.
8. **Manipulation bright line:** measuring funding, premium, and forced flow is research. Any analysis whose *output* is a recipe for pushing price or oracle into liquidation/funding boundaries is out of scope — hard abort.

## §2 Pre-baked facts (do not re-discover)

### 2.1 Hyperliquid REST (all `POST https://api.hyperliquid.xyz/info`, JSON body) — all free

- `{"type":"perpDexs"}` → 9 HIP-3 dexes: xyz, flx, vntl, hyna, km, mkts, cash, para, abcd. `verified` (prior session).
- `{"type":"metaAndAssetCtxs","dex":"xyz"}` → per-market snapshot: `funding` (hourly rate), `openInterest`, `oraclePx`, `markPx`, `premium`, `dayNtlVlm`. Snapshot only, no history. `verified`.
- `{"type":"fundingHistory","coin":"xyz:SKHX","startTime":<ms>}` → ≤500 rows/call, paginate by advancing `startTime` past the last row. History reaches market inception (SKHX returned 1,978 hourly rows ≈ 82 days in the Study-1 fetch). `verified`. Coin naming is `"dex:COIN"` throughout.
- `{"type":"candleSnapshot","req":{"coin":"xyz:SKHX","interval":"1h","startTime":<ms>,"endTime":<ms>}}` → OHLCV + trade count `n` + volume `v`. **`verified` 2026-07-10 for HIP-3 coins**: 1d candles for xyz:SKHX reach back to **2026-02-19** (inception). Intervals `1m…1d`. Max candles per request `assumed` ~5000 (1h × 142 days = 3,408 fits in one call — verify by comparing row count to requested span; paginate if short).
- `{"type":"predictedFundings"}` → **main-dex coins only; NO HIP-3 entries** (`verified` 2026-07-10 — grep for `dex:` returned nothing). Gives external-venue rates (BinPerp/BybitPerp) + HlPerp for majors — useful as hedge-leg reference for hyna, useless for HIP-3 prediction.
- **Epoch trap:** ms timestamps; 2026 dates start ≈ 1,767,225,600,000. A 2025-epoch typo returns `[]` silently, not an error (bitten during planning).

### 2.2 Funding mechanics — encode as HYPOTHESES for S-B, not facts

Recollection of HL docs (`assumed`, T0 doc-check must verify against current https://hyperliquid.gitbook.io docs and cite): funding settles **hourly**; rate ≈ clamp(interest-rate component + premium term, ±cap), where premium derives from (markPx − oraclePx)/oraclePx sampled through the hour. HIP-3 markets use the **deployer-provided oracle**, so the deployer indirectly controls funding. Whether HIP-3 uses the same clamp/cap and interest component as core perps is UNKNOWN — that is precisely what S-B measures empirically. Do not hardcode any formula constant without a doc citation + empirical reconciliation.

### 2.3 CoinAPI flat files (only needed for S-B; everything else is free/on-disk)

Access: endpoint `https://s3.flatfiles.coinapi.io/`, bucket `coinapi`, access key = `COINAPI_API_KEY` from repo `.env`, secret = literal `coinapi`, `curl --aws-sigv4 "aws:amz:us-east-1:s3"`. zsh eats `$VAR:c` — always `${VAR}`. Use `charybdis/ffs3.py`: it already has the spend meter, 8-way concurrency, 640 RPM limiter, 429/403 backoff, manifest/dry-run/resume discipline. Tier 3 limits: concurrency 8, 640 RPM.

- Oracle feed: `T-HLORACLEPRICES` under `E-HYPERLIQUIDL4/`, hourly partitions `D-YYYYMMDDHH`, first observed partition **2026-06-17 16:00 UTC** (inception unverified — open follow-up). Schema (verified on disk): `time_exchange;time_coinapi;coin_id;update_class;mark_px;mark_daily_px;oracle_px;oracle_daily_px;external_perp_px;external_perp_daily_px;spot_px_input;mark_px_input;external_perp_px_input`. `update_class ∈ {Deployer, Fallback}`.
- **WART:** oracle files are keyed by BARE coin (`S-SKHX`, `S-GOLD`) — multi-dex underliers interleave rows from several dexes with NO dex column. SKHX/SMSN are single-dex (xyz only) → clean. SP500-family twins collide → disambiguate by price-level clustering against per-dex REST `oraclePx` snapshots, or scope S-B to single-dex coins.
- Meter prices unknown SKUs at the Trades tier ($24/$12/$6 per GB/day) conservatively — the T5 oracle pulls billed ~$15.82 for SKHX/SMSN-scale data; whole-shortlist oracle history should fit well inside the $60 ceiling. ALWAYS list + dry-run before pulling (T4 gate).

### 2.4 On disk already (from Studies 1–2 — inventory `data/` before pulling anything)

- `data/reports/study1_funding.parquet` — hourly funding, 8 index markets, full history to 2026-07-09.
- `data/reports/forced_flow_conditioning_funding_proxy.parquet` + `forced_flow_events_proxy.parquet` (2,573 proxy events with wallets) + anatomy/coverage parquets.
- L2-era trades/books/quotes for the 8 index markets (2026-03-11→06-08); L4-era trades+quotes for the same (2026-05-08→…); SKHX/SMSN L4 trades (2026-05-27→07-08) + T7 event-window books; some SKHX/SMSN oracle files from T5 (inventory exactly what partitions exist before ordering more).
- Reusable code: `loaders.py` (streaming CSV.gz scans), `book.py` (L2 reconstructor), `calendars.py` (NYSE/KRX sessions, tz-aware; naive-UTC join trap documented), `markout.py` (cluster bootstrap), `forced_flow.py`, `ffs3.py`.
- Known data warts: 6 corrupt gzips at `D-2026052715`; `time_coinapi−time_exchange` has a fat tail (mean 110s, 92% ≤1s) — never use `time_coinapi` as a clock; 774 early L4 files lack `user_taker`.

### 2.5 Funding landscape snapshot (2026-07-09 probes, for orientation — S-A re-measures properly)

xyz:SKHX +340% APR instantaneous / +72% 21-day mean / 73% of hours positive / reported OI ≈ $483M. xyz:SMSN +46% mean. xyz:SMH +34%. xyz:SP500 +2.3%. km:US500 ≈ 0. hyna:BTC +6.5% (venue near-zero volume, likely dead). Full 289-market snapshot exists in the prior session scratchpad but is session-temporary — S-A regenerates it durably.

### 2.6 Fees (for cost-aware backtests)

Maker 1.5 bps, taker 4.5 bps, both `assumed` (HL base tier). HIP-3 deployer fee scaling exists (hyna `deployerFeeScale 0.1111` observed; others unknown) — T0 doc-check verifies and records per-dex effective fees as a small table; every backtest reads fees from that one table, marked `assumed` or `verified` per cell.

## §3 Pre-registered sub-studies, metrics, falsification criteria

Registered before any new data is examined. Reports state numbers + interval geometry only; the operator applies these criteria.

### S-A Census & persistence (free)
Full `fundingHistory` for **all ~289 HIP-3 markets** + main-dex hedge references (BTC, ETH, and any main-dex twin of a HIP-3 underlier). Per market: mean/median APR, % hours positive, AC(1) and AC(24) of hourly rates, funding-shock half-life (AR(1) fit), regime durations above {25%, 100%, 300%} APR, week-over-week cross-sectional rank correlation (Spearman) of mean funding. Join current OI + `dayNtlVlm` snapshots → **carry-capacity map** (funding × size). Primary output: ranked table with CIs (market×6h clusters).
*Decision use:* identifies the harvestable set. **Persistence bar:** a market is carry-relevant only if week-over-week funding rank correlation ≥ 0.5 and shock half-life ≥ 24h — below that, funding isn't a signal, it's noise.

### S-B Mechanics reconciliation (the one paid pull)
For a scoped coin set (xyz:SKHX, xyz:SMSN — single-dex, clean — plus xyz:SP500 and one km coin if the bare-coin wart is tractable): recompute predicted funding for hour h from the oracle-feed premium during h−1→h (per the T0-verified doc formula) and regress realized `fundingHistory` on it. Metrics: residual distribution (bps/hr), R², clamp events observed, residual-vs-`update_class` (Deployer vs Fallback) split, and **prediction lead time** — at minute m of the hour, how much of hour-end funding is already determined (R² as a function of m).
*Falsification (F-B):* if R² < 0.8 at minute 50, funding is not premium-mechanical on HIP-3 (deployer discretion or unknown formula) → all *prediction*-based strategies (S-D) die; carry (S-C) survives since it uses realized funding. If R² ≥ 0.95 at minute 50, funding is effectively knowable pre-settlement → S-D upgraded.

### S-C Cross-sectional carry backtest (free — the money question) — correctness-review mandatory
Universe: all HIP-3 markets passing a liquidity floor (dayNtlVlm > $1M `tunable`). Data: 1h candles + funding history, both free. Strategies, all cost-aware (fees per §2.6 + half-spread from on-disk books where available, else spread `assumed` = 2× the Study-1 observed segment median for that market class, labeled):
1. **Short-only decile carry:** short top-decile trailing-7d-mean funding, equal weight, rebalance daily and 8-hourly (both).
2. **Long-short decile carry:** add long bottom decile.
3. **Single-name hedged short:** short SKHX vs long {SMH, KR200, EWY} hedge basket, β from trailing 30d 1h-candle regression, plus unhedged variant.
Decomposition per strategy: **funding PnL vs price PnL vs cost PnL**, cumulative curves, Sharpe (cluster-bootstrap CI), max drawdown, worst single squeeze (link Study-2 overshoot anatomy for intra-hour tails candles can't see — state as a named limitation).
*Falsification (F-C):* carry is dead if net total return CI includes 0 at the portfolio level, or if price PnL ≤ −(funding PnL) — i.e., high funding is fair compensation. Pre-registered prior to beat: the market is not stupid; +340% APR probably prices real squeeze risk. The interesting outcome is *either* a clean rejection *or* a quantified residual.
*No-look-ahead check:* signal = funding known at rebalance time; returns = candle closes strictly after.

### S-D Funding-clock effects (free / on-disk)
In high-funding markets: price and flow behavior around the hourly settlement. Metrics: mean return in the {−10m, −5m, −1m, +1m, +5m, +10m} brackets around settlement, split by funding sign/size decile; premium decay into settlement (REST snapshots forward + oracle feed where on disk); on-disk L4 SKHX/SMSN: do repeat wallets open shorts pre-settlement and close after (position-proxy from signed taker flow per wallet)?
*Falsification (F-D):* no bracket's return CI separates from the matched non-settlement baseline bracket → no clock effect. Only meaningful if F-B showed funding is predictable.

### S-E Cross-dex funding spreads (free + on-disk books)
Twin sets: SP500 on {xyz, km, cash, flx}; USA100/USTECH twins; NVDA multi-dex; GOLD (6 dexes); any others S-A surfaces. Metrics: pairwise funding differential time series — mean |diff| APR, persistence (half-life), % time |diff| > breakeven, where breakeven = round-trip costs (2 legs × entry+exit, maker and taker variants) amortized over the observed persistence horizon; **twin-basis risk** = vol and max excursion of (pxA − pxB)/pxB from 1h candles (different deployer oracles → the legs CAN diverge; this is the tail risk of the "riskless" spread).
*Falsification (F-E):* dead if breakeven-exceeding episodes have median duration < 2× the cost-amortization horizon, or twin-basis max excursion swamps the funding differential at the 95th percentile.

### S-F Funding → forced-flow linkage (on-disk; closes the T8 gap)
Event *rate* per funding regime: proxy-event counts per bucket ÷ **time spent in bucket** (the normalization T8 lacked), with CIs. Wallet bridge: do wallets accumulating longs during ≥100% APR regimes subsequently appear as burst takers in proxy events? Deliverable: funding level/change as a leading indicator — hazard-style table of P(event within 24h | funding bucket).
*Falsification (F-F):* rate ratios' CIs include 1 across all high-vs-low bucket comparisons → funding does not time forced flow (its role stays market-*selection* only).

## §4 Gates

- **G-F1 (paid-pull gate, before T4 executes):** list + dry-run the oracle manifest. If projected > $40, trim scope (fewer coins/days) to fit; if it can't fit under the $60 ceiling with S-B still answerable, escalate with the dry-run numbers instead of pulling. Confirm `data/spend.json` cumulative + console balance sanity first.
- **G-F2 (mechanics gate, after T4):** F-B outcome routes T5 — if funding is unpredictable, T5 (funding-clock) is descoped to the settlement-bracket returns only (skip prediction framing) and the report says why.
- **G-F3 (REST budget):** T0 estimates total call count before harvesting (~289 markets × (funding pages + 2 candle calls) ≈ 2–3k calls ≈ 25–45 min at 1–2 rps). If an endpoint 429s persistently at 1 rps, halve and continue; never hammer.
- **G-F4 (plan-stale):** two consecutive task escalations → stop, re-plan with operator.

## §5 Task queue

Protocol per agentic-loop: SEAM-CARD (Explore) → IMPL-CARD (codex, TDD with pasted RED→GREEN) → REVIEW-CARD (adversarial; + correctness on T3/T4/T6) → fix ≤2 passes → commit → one ledger row. Cards are fixed-size; no file dumps to the orchestrator.

| id | task | needs | check (RED→GREEN) | notes |
|---|---|---|---|---|
| T0 | REST harvester: `charybdis/hl_rest.py` — paginated `fundingHistory`, `candleSnapshot`, `metaAndAssetCtxs`/`perpDexs` snapshots; disk cache under `data/rest_cache/`; rate limiter; **doc-check deliverable**: funding-formula citation + per-dex fee table (§2.2, §2.6) | — | pagination unit test on a 2-page fixture; live smoke: SKHX funding row-count ≥ 1,978 and 1d candles reach 2026-02-19 | cache = reproducibility; all later tasks read cache only |
| T1 | Harvest run: all 9 dexes × all markets — funding full history + 1h/1d candles + snapshots; census parquet | T0 | row-count reconciliation vs per-market inception; zero-gap audit per market (funding is hourly — assert no missing hours or record them) | free; ~2–3k calls; G-F3 |
| T2 | S-A census & persistence + carry-capacity map + report | T1 | stats unit-tested on synthetic AR(1) fixture with known half-life; report cells recomputed from parquet by reviewer | universe definition for T3 frozen here |
| T3 | S-C carry backtests (3 strategies × 2 rebalance freqs) + decomposition report | T2 | **correctness review mandatory**; no-look-ahead test: shifting funding by +1h must change PnL; fee/cost table single-sourced | the money task |
| T4 | S-B: oracle manifest + dry-run (**G-F1**), pull, premium→funding reconciliation + report | T0 | **correctness review**; RED: reconciliation on a synthetic premium fixture with known formula; GREEN: real R² table by minute-of-hour | the only paid task |
| T5 | S-D funding-clock brackets (+ wallet pre/post-settlement flow on SKHX/SMSN L4) | T1, G-F2 | bracket assignment unit test across a settlement boundary; baseline-matching mirrors Study-2 matched-pair code | on-disk + cache |
| T6 | S-E cross-dex spreads + twin-basis risk + breakeven table | T1 | **correctness review**; breakeven arithmetic unit-tested; twin alignment test (same underlier, different dex prefixes) | uses pre-6/18 books for spread costs where available |
| T7 | S-F event-rate normalization + wallet bridge | T1 + Study-2 parquets | rate = events/bucket-hours with exposure-time denominator unit-tested; hazard table | closes the T8 gap |
| T8 | Consolidated Study-3 report + spend accounting + ledger close-out + follow-ups | all | report↔parquet spot-recompute by reviewer (≥4 cells); no verdicts | mirror `summary_studies_1_2` format |

Parallelism: after T1 lands, T2 and T4 can run concurrently; T5–T7 fan out after their inputs. Paid T4 sits behind free T0–T2 so a credit lockout never blocks the free spine.

## §6 Escalation / abort (unchanged hard lines)

- Anything touching order placement, wallets-as-actors, or keys beyond reading `COINAPI_API_KEY` → **hard abort** (research-only repo).
- §1.8 manipulation bright line → hard abort.
- Unknown external schema with no fixture → escalate, never guess.
- Full-test-tree runs or OOM → abort the task, report (constraint violation).
- CoinAPI 403 credit lockout mid-pull → write resume manifest, continue free tasks, note for morning (established pattern).

## §7 Morning deliverables

1. `docs/reports/study3_funding_census_<date>.md` (S-A + capacity map)
2. `docs/reports/study3_carry_backtest_<date>.md` (S-C decomposition, the headline)
3. `docs/reports/study3_mechanics_<date>.md` (S-B R²-by-minute + oracle-class splits)
4. `docs/reports/study3_spreads_clock_events_<date>.md` (S-D/E/F) — or split if large
5. `docs/reports/summary_study3_<date>.md` + spend accounting + updated `LEDGER.md` with follow-ups
6. Parquet artifacts under `data/reports/` with column-level provenance lines in each report, per house style

**Operator override points (pre-registered knobs):** liquidity floor $1M; decile width; trailing-mean window 7d; hedge-β window 30d; S-A persistence bars (0.5 rank-corr / 24h half-life); F-B R² thresholds (0.8/0.95); assumed fees pending T0 verification.
