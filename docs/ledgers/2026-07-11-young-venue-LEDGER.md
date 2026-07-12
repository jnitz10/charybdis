# Session ledger 2026-07-11: Paradex recon → funding post-mortem → young-venue edges

Handoff doc for context compaction. Everything below is also reflected in memory
(`study3-funding-findings`, `walletflow-concentration`, `research-console`,
`feedback-negative-results-framing`) — this file is the detailed session record.

## One-paragraph summary

Started as Paradex recon, became a full post-mortem of funding as a signal
(dead as standalone alpha everywhere tested), and ended with three live objects:
the **Monday oracle-reanchor effect**, the **listing week-1 elevation**, and —
strongest — the **forced-flow harvester** (bids-only passive liquidity provision
at 100–200bp), which passed four successive gates (cross-market generality,
worst-case exits, passive exits, oracle conditioning). A $31.15 CoinAPI pull of
17 single-name trades + 27-symbol oracle data is IN FLIGHT to extend it. The
unifying thesis: all live edges are the same object — **perp overshoot relative
to its oracle anchor** — at different timescales (unhedged convergence trading,
not stat arb: the anchor is contractual via funding/settlement).

## Live findings (with the numbers)

1. **FF harvester** (the centerpiece). Rest bids 100–200bp below a 1-min-repegged
   5-min-median ref on 13 HIP-3 markets; conservative trade-through fill model.
   - Pooled δ≥100 fills: +32.8bp/fill net at 30min, t=+5.43 (2,164 fills, 86
     fill-days); robust ex-SKHX (+30.3, t=4.4); positive every month Mar–Jul;
     25bp quoting adversely selected on ALL 13 markets; EWY/XYZ100 negative.
   - Exit gate: crossing the touch at t+30 costs 22–27bp → pooled dies (−7.1),
     ASKS die (−23.5), BIDS survive (+17.7, t=2.0 = floor). Paper profits
     concentrate where quotes are broken (sane-quote mark edge is +16 not +33).
     Median touch depth $300 → sub-$1k clips.
   - Passive-exit gate: rest exit at half-reversion → 89% passive fill, blended
     +40.0bp (t=9.7); full-reversion 69%/+73.9. Penalizing the 11–22% no-quote
     fills at −150bp → **planning number ~+19–25bp/fill, ~9 fills/day**.
   - Oracle conditioning (164 SKHX/SMSN fills, Jun17–Jul8): INVERTS the glitch
     hypothesis — oracle-flat perp crashes LOSE −25.7bp (perp leads info);
     real-underlying-move overshoots WIN +17.1bp (41% of fills). Live rule
     candidate: quote wide only when oracle confirms the move. t's 1.2–1.6 →
     design input, needs full-sample validation (oracle pull in flight).
   - Artifacts: `data/reports/ff_harvest_fills.parquet` (SKHX/SMSN v1),
     `ff_harvest_fills_all.parquet` (13 mkts), `ff_exit_study.parquet`,
     `ff_passive_exit.parquet`, `ff_minute_bars.parquet` + `ff_bars/` shards.
     Scripts in session scratchpad (ff_harvest_backtest.py, ff_harvest_all.py,
     ff_exit_study.py, ff_passive_exit.py) — scratchpad is session-temp; rescue
     to repo if wanted.

2. **Monday effect** (xyz equities): Monday mean +0.79%/wk t=+2.91 (26 wks,
   week-clustered) vs +0.03% other days; driven by weekend-DOWN names (+0.75%
   t=2.07); up-weekend names flat. Daily session boundaries NULL (Korea 00:00
   re-anchor, US RTH open, Tue–Fri) → needs the long weekend window; may be
   weekend risk premium rather than pure re-anchor. Forward-test candidate #1.
   NOTE: Monday-exclusion attribution showed the gated-funding candidate's
   significance was riding on Mondays (ex-Monday CI includes 0) → funding tilt
   demoted to unproven overlay.

3. **Listing lifecycle**: week-1 |daily ret| +0.32pp vs weeks 3–8, t=+2.93 over
   128 in-window births; week-1 |funding| 50% hotter; ~5 births/week → basis
   for a new-listing watch program.

4. **Wallet concentration** (panels built, factor blocked on breadth):
   flx = single-MM (top-1 maker 81–85%); xyz flagships competitive (top-1
   11.9–16%, 265–626 makers); Korea whales persistent (autocorr .65–.72);
   brittleness→instability suggestive (t≈1.5, 29 days). Panels:
   `walletflow_taker_daily.parquet`, `walletflow_maker_daily.parquet`,
   `walletflow_taker_signed_daily.parquet`.

## Dead ends (do not revisit without new data)

Funding level carry both directions (S-C + S-C-bis: long +60.6% but CI incl 0,
0.74 beta-correlated); funding impulse (reversal only in z>2 tail on HIP-3
−1.4%/24h t=−2.9, but FAILED main-dex replication — venue-specific or noise);
main-dex crypto funding fully priced (level IC 0.000, impulse +0.011 t=1.2);
cross-dex twin arb (S-E 0/57); Paradex options pickoffs (quotes bracket Deribit
fair ±15–35%); Amihud factor (t=−0.35); premium residual (MIS-SPECIFIED — API
premium units ≠ S-B oracle-feed premium, k came out 0.04 vs 0.567; needs
study3_mechanics normalization); twin lead-lag from candles (0 pairs with ≥800
co-traded hours — needs L4 mid-quotes); OI quadrants (snapshots single-timestamp).

Paradex itself: $8.1M/day real volume, options 22/1763 traded (combo legs
double-count), tight-but-thin books; only edge = XP/DIME farming at ~zero cost.
Funding feed there is 5s-granularity free REST if ever needed.

## Post-pull results (2026-07-11 night)

- Pull COMPLETE: 26,878 files, $31.15, spend $148.08, no pauses.
- **Single-name harvester backtest** (`ff_harvest_fills_singlenames.parquet`,
  22,185 fills, 17 names): wide bids pooled +0.0bp t=0.00 — the edge does NOT
  extend to US single names. Window-matched control: original 13 markets over
  the same Jun1–Jul8 window still +23.8bp t=2.42 → market selection, not
  decay. 25bp adverse selection (−6.9 t=−3.1) and ask-death (−31 t=−3.1)
  DO replicate. Deployment filter: thin/concentrated markets (wallet panels).
- Oracle archive starts 2026-06-17 (all symbols); includes venue mark_px at 3s.
  Minute shards: `data/reports/oracle_bars/{SYM}.parquet` (30 syms).
  Trade minute shards for the 17 names: `data/reports/ff_bars_sn/`.
- **Oracle conditioning, full sample (1,728 wide fills): REVERSES the 164-fill
  pilot.** Perp-only dislocations (oracle flat 30m) win +44.7bp t=+3.16 (bids);
  oracle-confirmed fills lose −25.3bp bids / −34.3 t=−2.0 asks. Robust across
  15/30m windows and 0.25/0.5·δ thresholds. Live rule: fade ONLY when the
  oracle does NOT confirm. Conditioning doubles the 13-mkt edge (+59.8 t=2.76)
  and rescues a single-name pocket (+27.8 t=1.29).
  `ff_oracle_condition_full.parquet`; script ff_oracle_condition_full.py.

- **Basis event study** (`ff_basis_events.parquet`, 5,035 events): residual
  perp−oracle gaps converge any day. T=50 oracle-opposed +35.3bp/30m t=4.64;
  T=100 confirmed-residual +65.3bp/2h t=3.52. Sat/Sun have most events and
  positive h2 (t≈2.1–2.5); Monday per-event NOT special → Monday effect =
  weekend gap accumulation, not calendar premium. Markout-not-executable
  caveat applies. All three queued post-pull analyses are now DONE.

## In flight RIGHT NOW

- **CoinAPI pull** (background task, scratchpad `pull_singlenames.py`): 17
  single names' L4 trades (INTC HIMS MSTR CRCL HOOD COIN MU MRVL TSLA NVDA PLTR
  RKLB NBIS AMD ARM BE RIVN, Jun1–Jul8) + oracle for those + 10 index syms.
  26,878 files ≈ 1.6GB, **$31.15**, projected running total $148.08 (operator
  budget was $60 for this pull; global PAUSE_USD=178). Manifest:
  `data/pull_singlenames_manifest.json`; spend meters into `data/spend.json`.
  MU is the biggest single name (302MB), then MRVL/NVDA (memory-chip complex).
- On completion, queued analyses in order:
  1. Harvester backtest on the 17 single names (reuse ff_harvest_all.py pattern;
     per-market shards — background jobs get KILLED sometimes, make parses
     resumable).
  2. Oracle-conditioning on the full fill sample (extend the 164-fill study).
  3. **Generalized basis/overshoot study**: minute-level perp−oracle basis, ANY
     day entries; test whether gap size subsumes the Monday effect. Signal
     discipline from the 164-fill study: overshoot-of-confirmed-move wins,
     naked discounts lose.

## Backlog / next-session menu

- Basis study (above) — likely highest value.
- Twin-hedged overshoot structure (short dislocated perp vs long its twin) —
  untested; S-E only killed the funding-spread version.
- Premium-residual redo with correct units.
- Live pilot design for harvester (queue/latency/size unknowns are live-only).
- Forward tests: Monday effect + listing effect on accruing data ($0, just time).
- Console: trade-overlay feature recorded in `docs/backlog/console-trade-overlay.md`
  (lightweight-charts markers suffice; fills parquets are the data).

## Session gotchas (operational)

- **Put results in the FINAL message of a turn** — text before trailing tool
  calls wasn't rendered for the operator (caused 4 "where are the results"
  asks). Bookkeeping edits first, results last. Also: no scare quotes / wry
  framing on outcomes; lead negative results with what the thing IS good for
  (both now in feedback memory).
- Background Bash jobs killed twice mid-parse (~13k-file loops) — make long
  parses resumable (per-market shards) and print progress.
- `uv run` must run from repo root (scratchpad cwd → no polars).
- rtk hook mangles some grep output; `rtk proxy grep` for raw.
- CoinAPI quote feed: ask side degrades after ~2026-06-18 (crossed books) —
  L4-quote analyses trustworthy only 2026-05-08→06-18; oracle files mix dexes
  per bare symbol (disambiguate by price scale ±30%).
- HL fundingHistory ≈ recent-only at fine grain; funding_rate_8h field exists;
  Paradex funding is 5s cadence.

## Spend

$116.92 start → $148.08 projected after this pull. Cumulative program still
under the (now-void as disk, $178 as spend) plan gates.
