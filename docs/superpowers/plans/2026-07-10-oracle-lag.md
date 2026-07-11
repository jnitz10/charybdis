# Study 4 — Cross-Dex Oracle-Lag Taking (grinder-loop handoff)

**Date:** 2026-07-10. **Operator:** jnitz. **Orchestrator:** Opus via agentic-loop skill.
**Implementer (all tasks):** GPT5.6-High via `codex:codex-rescue`. **Reviewer:** `compound-engineering:ce-adversarial-reviewer` every task; add `ce-correctness-reviewer` on T2 and T5 (money math).
**Ledger:** `LEDGER.md` at repo root (fresh). Prior ledgers: `docs/ledgers/2026-07-09-studies-1-2-LEDGER.md`, `docs/ledgers/2026-07-10-study3-LEDGER.md`.

## §0 Mission and budget

Kill-test for **strategy prior #3** (`docs/2026-07-05-strategy-priors.md`): *"Four independent NVDA oracles, six GOLDs: someone's book is stale after every sharp move… the oracle-forensics study produces the lead/lag numbers for free; build only if they're screaming."* Studies 1–3 killed priors #1, forced-flow, and every funding angle. This study measures whether taking stale quotes on a lagging dex after its twin has moved earns money **net of taker fees**, and whether the niche is already occupied by faster snipers.

Why this is plausible where the others died: Study 1 measured passive maker markouts of −0.5 to −1.5 bps *gross* on the liquid index perps — the aggressor side of those same fills earns +0.5 to +1.5 bps gross **unconditionally**. That's below the ~4.5 bps taker fee, so blind taking loses; the entire question is whether *conditioning on a twin-leader move* concentrates enough of that edge into few enough fills to clear the fee. Pre-registered prior: probably marginal — the priors doc itself calls it a knife fight on the toxic side of the table. The cheap, decisive measurement is the point.

**Budget:** cumulative meter $116.92. Study-4 new-spend ceiling **$60, pause-line semantics** (stop downloads at $58 projected, finish analyses on data in hand, write RESUME state). The core study (T0–T4) is **$0** — everything runs on data already on disk. The only paid task (T5, NVDA/GOLD twin expansion) sits behind a *results* gate (G-O1) as well as the budget gate: per the priors doc, expand only if the free measurements are screaming. CoinAPI balance ≈ $75 UNVERIFIED; auto-recharge KNOWN BROKEN (support ticket outstanding) — 403 lockout mid-pull → resume manifest, continue free tasks.

**Run mode:** autonomous to the cap (standing operator directive). Surface only for true blockers, G-O2 plan-stale, or the pause line.

## §1 Binding design rules (inherited — violations are BLOCKERs)

1. **No look-ahead.** A signal at time t uses only events with `time_exchange` strictly earlier than t. **Same-chain quantization rule (new, critical):** all HIP-3 markets settle on the same Hyperliquid chain, so cross-market `time_exchange` values share one clock but are block-quantized — within-timestamp cross-market ordering is UNKNOWN. A leader event and a lagger execution at the SAME timestamp must be treated as unordered → the signal is unusable for that execution (drop, count, report the drop rate — Study-1 ADV-3 convention extended cross-market). Lead/lag resolution is bounded below by block cadence; measure and report the observed timestamp granularity per market rather than assuming it.
2. **Executable prices only.** Post-2026-06-18 CoinAPI quotes AND books are POISONED (frozen ask, phantom limits). Book-based windows: L2 era 2026-03-11→06-08 (clean, on disk, 8 index markets) and L4 era 2026-05-08→06-18 only. Trades and the oracle feed are unaffected through 07-08.
3. **Cluster-robust uncertainty:** reuse `charybdis.markout` cluster bootstrap (market×UTC-6h, 2,000 resamples, seed 0, 95% percentile, min G=5 → "insufficient evidence"). For pair-level statistics cluster on pair×UTC-6h (Study-3 S-E precedent).
4. **Memory:** `systemd-run --user --scope -q -p MemoryMax=6G -p MemorySwapMax=0 uv run …`; `prlimit --as=6442450944` fallback. Streaming/projected scans (`loaders.py` patterns).
5. **Null results are valid. No verdicts in reports** — numbers, CIs, interval geometry, pre-registered criterion statuses only.
6. **Trust the file, not the doc.** `verified` facts below were checked on 2026-07-10; `assumed` facts must be verified by the first task that depends on them.
7. **Bright line:** measuring stale quotes and sniper behavior is research. Nothing here designs *pushing* price/oracle. Taking displayed liquidity after public information is ordinary trading; that's the object of study.
8. Research-only repo: no order placement, no wallets-as-actors, no keys beyond `COINAPI_API_KEY` in `.env`.

## §2 Pre-baked facts (do not re-discover)

### 2.1 On disk (verified by inventory 2026-07-10)

- **L2-era books/trades/quotes, 8 index markets** (xyz:SP500, km:US500, flx:USA500, cash:USA500, km:USTECH, xyz:XYZ100, flx:USA100, km:SMALL2000), daily partitions 2026-03-11→06-08 under `data/T-LIMITBOOK_FULL/`, `data/T-TRADES/`, `data/T-QUOTES/`. This gives THREE clean twin groups with books: **SP500 {xyz, km, cash, flx}**, **USA100 {xyz:XYZ100, km:USTECH, flx:USA100}**, and SMALL2000 (no twin — control market).
- **L4-era trades+quotes** for the same 8 markets from 2026-05-08 (wallet-attributed trades; quotes/books usable to 06-18 only). Overlap window **2026-05-08→06-08** has BOTH clean books AND wallets → the sniper-census window.
- **SKHX/SMSN L4 trades** 2026-05-27→07-08 + T7 event-window books.
- **Oracle feed (`data/T-HLORACLEPRICES/`, 498 hourly partitions each, 2026-06-17 16:00→07-08): SKHX, SMSN, and GOLD.** GOLD is multi-dex → the bare-coin collision wart is PRESENT in that file set; SKHX/SMSN are single-dex (clean). Schema: `time_exchange;time_coinapi;coin_id;update_class;mark_px;…;oracle_px;…;external_perp_px;…;spot_px_input;mark_px_input;external_perp_px_input`, `update_class ∈ {Deployer, Fallback}`.
- Study-3 REST cache (`data/rest_cache/`): 1h/1d candles + funding all markets; fee table `data/reports/study3_fee_table.parquet` (effective maker/taker per dex — taker values `assumed` pending doc verification, single-sourced).
- Reusable code: `loaders.py`, `book.py` (L2 reconstructor + sanitation counters), `markout.py` (bootstrap + markout conventions), `study2.py` matched-window machinery, S-B premium/minute-curve code from Study 3.
- Warts inherited: 6 corrupt gzips at `D-2026052715`; 774 early L4 files lack `user_taker`; `time_coinapi` fat tail (mean 110s — never a clock; use `time_exchange` only); one-sided L1 rows must be skipped (T2-A1 rule); tz-naive timestamps are UTC.

### 2.2 Twin dex maps (from Study-3 audited underlier map, `study3_universe.parquet` / S-E)

SP500 = {xyz:SP500, km:US500, cash:USA500, flx:USA500} (+mkts:US500 REST-only — no flat files for mkts, unresolved vendor gap). USA100 = {xyz:XYZ100, km:USTECH, flx:USA100} (+mkts:USTECH REST-only). NVDA = {xyz, km, cash, flx}. GOLD = {xyz, km, cash, flx}. SILVER = {xyz, km, cash, flx}. TSLA = {xyz, km, cash, flx}. Index twins are quoted at DIFFERENT unit scales (km:US500≈700 vs xyz:SP500≈7365) — all cross-dex price comparison in **log-return / log-ratio space** (Study-3 S-E lesson, already burned once).

### 2.3 Known market-quality context (orient thresholds)

Study-1 spreads (bps, RTH/off-hours/weekend medians): xyz:SP500 0.36/0.26/0.47; km:US500 0.36/0.28/0.59; cash:USA500 0.25/0.20/0.45; flx:USA500 4.3/5.2/35.4; xyz:XYZ100 0.48/0.41/0.45; flx:USA100 6.1/12.1/134. Touch depth spans ~3–900 units. Maker markout −2 to −3 bps net of 1.5 bps fee ⇒ gross adverse move past the touch ≈ 0.5–1.5 bps at 30s unconditionally. Signals must therefore select moments with expected lagger repricing ≫ 4.5 bps for taker profit. flx books are wide/thin — stale-quote distance there can be tens of bps, which is exactly where the priors expect the fish to be; but flx L2/L4 trade-count agreement was 22–25%, so treat flx measurements with its documented feed-sparsity caveat.

### 2.4 Fees

Effective taker per dex from `study3_fee_table.parquet` (`assumed` 4.5 bps base × deployer scale until T0's doc-check verifies; hyna scale 0.1111 verified). All backtests read the table; report cells label `assumed`/`verified`. Exit-cost scenarios are pre-registered in §3 S4-B — never assume free exit.

## §3 Pre-registered sub-studies, metrics, falsification criteria

### S4-A Twin lead/lag census (free, L2 era, books on disk)
For each twin pair (SP500 ×6 pairs, USA100 ×3 pairs): cross-correlation of mid log-returns on {100ms, 250ms, 1s, 5s} grids; lead operationalized as the lag maximizing cross-correlation + Hayashi–Yoshida-style asynchronous covariance as robustness. Segment by {RTH, off-hours-weekday, weekend} (calendars.py). Divergence census: after leader mid moves ≥θ bps within τ (grid: θ ∈ {5, 10, 20, 50}, τ ∈ {1s, 5s}), distribution of (a) lagger touch response time, (b) peak stale distance = leader-implied fair vs lagger touch (log space), (c) time-to-converge.
*Output:* per-pair lead table with CIs; stale-episode census. Pure measurement — no kill criterion; feeds S4-B thresholds (which are pre-registered above, not tuned post hoc).

### S4-B Conditional taker backtest (free, L2 era — the kill test) — correctness review mandatory
Mirror of the Study-1 engine, aggressor side. Signal: leader mid moved ≥θ within τ AND lagger touch has not repriced ≥θ/2 in the same window AND signal block strictly precedes execution block (§1.1). Action: marketable order into the lagger's stale side at touch, fill size = min(displayed touch size, notional cap $5k); walk deeper levels as a size sensitivity. Execution delay sensitivity: signal→execution latency δ ∈ {0 (upper bound, unrealistic), 250ms, 1s, 3s} — fills execute against the reconstructed book **as of t+δ** (if the touch repriced within δ, the opportunity is gone: count, don't fill — this is the occupancy tax made explicit).
Primary metric: **30s mid-to-mid markout net of entry taker fee**, horizons {1s, 5s, 30s, 2m, 10m}, per pair × segment × (θ, τ, δ) cell, cluster-bootstrap CIs. Exit-cost sensitivity rows: net markout minus {0, half-spread-at-horizon, full taker fee} for the exit leg. Opportunity census per cell: signals/day, fills/day, median takeable notional, gross $/day at $5k cap.
*Falsification (F4-B) — prior #3 is DEAD if:* no (pair, segment, θ, τ) cell at δ≥250ms has 30s net-markout CI > 0 under the middle exit-cost scenario; *marginal* if positive cells exist but census gross < $50/day aggregate at the $5k cap. *Screaming* (G-O1 trigger): ≥3 independent cells with CI > 0 at δ=1s AND aggregate ≥ $500/day. These labels are pre-registered so the morning read is mechanical.

### S4-C Sniper census (free, L4 overlap 2026-05-08→06-08 + SKHX/SMSN to 07-08)
For every S4-B signal in the wallet window: who actually took the stale side first — reaction-time distribution (signal→first aggressive fill), taker-wallet concentration (top-10 share of signal-following take volume), sniper wallet count and stability week-over-week, and the **residual curve**: fraction of stale-episode value still available at δ ∈ {250ms, 1s, 3s, 10s} after the fastest wallets have eaten. Cross-reference: are the sniper wallets also the Study-2 burst wallets?
*Output:* occupancy report. No kill criterion of its own — it explains WHY F4-B comes out how it comes out, and calibrates what a Tokyo-colo implementation could realistically capture.

### S4-D Oracle forensics (free, oracle feed on disk: SKHX, SMSN, GOLD)
(a) Update cadence: inter-update interval distribution by `update_class`, by market session (KRX open/closed for the Korean names), gaps > 10s census. (b) **Deployer re-mark risk** (the priors-doc fear): jumps in `oracle_px` ≥ 25 bps with no contemporaneous `external_perp_px`/`spot_px_input` move — count, size distribution, clustering. (c) Mark-vs-external lead/lag (reuse S-B minute-curve machinery). (d) **GOLD collision disambiguation prototype:** separate the interleaved multi-dex GOLD rows by price-level clustering against per-dex REST `oraclePx` snapshots; report achieved purity — this de-risks any future multi-dex oracle pull (S-B follow-up #9).
*Output:* oracle risk census. Feeds the risk section of any future live design; (d) is a reusability deliverable.

### S4-E Paid expansion — NVDA + GOLD twins (GATED, see G-O1)
L2-era (2026-03-11→06-08) books+trades+quotes for NVDA×{xyz,km,cash,flx} and GOLD×{xyz,km,cash,flx}; rerun S4-A + S4-B on them. Single names with real earnings/news flow and 4 independent oracles are the priors' marquee targets — but they're a paid bet, so they only run if the free markets already show signal or near-signal.
*Falsification:* same F4-B criteria applied to the expanded set; the combined report is the study's answer.

## §4 Gates

- **G-O1 (results gate for T5):** T5 is authorized only if S4-B produced ≥1 cell at δ≥250ms with 30s net-markout CI > 0 (any exit scenario) — i.e., *screaming or at least audibly humming*. If everything is dead at 250ms on the free set, write the null, skip T5, save the money. Budget sub-gate: dry-run manifest ≤ $45 or trim scope (GOLD-only or NVDA-only first by S4-A-analog liquidity).
- **G-O2 (plan-stale):** two consecutive task escalations → stop, re-plan with operator.
- **G-O3 (engine sanity):** before trusting S4-B, reproduce one Study-1 maker-side number with the taker-mode engine flipped back to maker mode (same fill, opposite sign convention) — cheap regression against a known-good result. Mismatch > tolerance → BLOCKER.

## §5 Task queue

Protocol per agentic-loop: SEAM-CARD (Explore) → IMPL-CARD (codex, TDD, pasted RED→GREEN) → REVIEW-CARD (adversarial; correctness on T2/T5) → fix ≤2 passes → commit → ledger row. Fresh subagent per stage; cards only.

| id | task | needs | check (RED→GREEN) | notes |
|---|---|---|---|---|
| T0 | Scaffold: twin-pair registry, signal library (`charybdis/oracle_lag.py` signals only), taker fee doc-check; timestamp-granularity probe per market (block quantization census, §1.1) | — | signal unit tests incl. same-timestamp unordered case (RED without the drop rule); granularity table from real files | small; freezes signal definitions |
| T1 | S4-A lead/lag + stale-episode census + report | T0 | Hayashi–Yoshida + xcorr validated on synthetic lagged series with known lead; report cells recomputed by reviewer | free |
| T2 | S4-B taker engine + backtest + report | T0, T1, G-O3 | **correctness review**; G-O3 maker-mode regression; no-look-ahead test: shifting leader stream +1 block must kill signals; delay test: δ=∞ ⇒ zero fills | the kill test |
| T3 | S4-C sniper census + residual curve + report | T2 signals | wallet reaction-time on synthetic fixture; concentration math unit-tested | L4 overlap window |
| T4 | S4-D oracle forensics + GOLD disambiguation prototype + report | T0 | re-mark detector on synthetic jump fixture; disambiguation purity metric on GOLD with REST ground truth | reuses S-B code |
| G-O1 | results + budget gate | T2 | — | routes T5 or skips to T6 |
| T5 | Paid pull NVDA+GOLD twins (dry-run ≤$45) + rerun S4-A/S4-B + report | G-O1 | **correctness review**; same engine, zero code changes expected — any needed change is a smell, escalate | only paid task |
| T6 | Consolidated Study-4 report + spend accounting + ledger close-out + follow-ups | all | report↔parquet spot-recompute (≥4 cells); no verdicts; F4-B statuses stated mechanically | mirror summary_study3 format |

Parallelism: T1/T4 independent after T0; T3 after T2's signal parquet lands. T5 last.

## §6 Escalation / abort (unchanged hard lines)

Order placement / wallets-as-actors / keys → hard abort. §1.7 bright line → hard abort. Unknown schema without fixture → escalate. Full-test-tree or OOM → abort task, report. CoinAPI 403 lockout → resume manifest, continue free tasks, morning note.

## §7 Morning deliverables

1. `docs/reports/study4_leadlag_census_<date>.md` (S4-A)
2. `docs/reports/study4_taker_backtest_<date>.md` (S4-B — the headline, with F4-B statuses)
3. `docs/reports/study4_sniper_census_<date>.md` (S4-C)
4. `docs/reports/study4_oracle_forensics_<date>.md` (S4-D incl. GOLD disambiguation purity)
5. If G-O1 passed: `docs/reports/study4_nvda_gold_<date>.md` (S4-E)
6. `docs/reports/summary_study4_<date>.md` + spend accounting + closed ledger

**Operator override points (pre-registered knobs):** θ/τ/δ grids; $5k notional cap; exit-cost scenario set; F4-B dollar thresholds ($50/$500 per day); G-O1 authorization criteria; NVDA-vs-GOLD-first ordering in T5.

**Phase-B note (not tonight's work):** if F4-B lands alive, the implementation question becomes latency — the sniper residual curve (S4-C) at δ≈1–5ms is what a Tokyo same-region box would see; that's the bridge to the Lightsail/EC2 capture-box thread already discussed.
