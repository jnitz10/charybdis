# LEDGER — Study 3: Funding Deep Dive (2026-07-10)

**Plan:** `docs/superpowers/plans/2026-07-10-funding-deep-dive.md` (read it first; §2 facts are pre-verified — do not re-discover; §3 criteria are pre-registered — do not re-litigate)
**Previous run:** Studies 1–2 complete — ledger archived at `docs/ledgers/2026-07-09-studies-1-2-LEDGER.md` (G2 census, deferred findings, and all handoff notes live there; Study-2 report references to "LEDGER.md" mean that file).
**Protocol:** agentic-loop. Orchestrator (Opus) never reads source / writes code. Implementer: GPT5.6-High via `codex:codex-rescue`. Reviewer: `ce-adversarial-reviewer` every task; + `ce-correctness-reviewer` on T3, T4, T6.
**Budget state:** cumulative meter $116.92 (Studies 1–2). Study-3 new-spend ceiling **$60, pause at $58 projected** (plan §0). CoinAPI balance ≈ $75 UNVERIFIED — sanity-check before T4's paid pull (G-F1). Auto-recharge KNOWN BROKEN; 403 lockout mid-pull = write resume manifest, continue free tasks.
**Operating mode:** autonomous to the cap (standing operator directive). Only surface for true blockers, G-F4 plan-stale, or the pause line. T4 is the ONLY paid task; everything else is free REST or on-disk data.

**Queue + next:** T0 → T1 → [T2 ‖ T4(G-F1)] → [T3 after T2] ‖ [T5(G-F2) T6 T7 after T1] → T8

| task | implementer | status | commit SHA | check | verdict | follow-ups | decision? |
|---|---|---|---|---|---|---|---|
| T0 REST harvester + doc-check (formula citation, fee table) | codex GPT5.6-High | DONE | 69e75a6 | 10 tests GREEN; adv-review FIX-FIRST → HIGH cache-poison + MED numpy-int + LOW candle-drop FIXED | formula VERIFIED vs gitbook; HIP-3 clamp assumed→T4; fee table @ data/reports/study3_fee_table.parquet | none |
| — T0 smoke/estimate | — | — | — | SKHX 3,381 funding rows, candles to 2026-02-19; G-F3 T1≈2,611 calls ~22min@2rps | live metadata shows **225** universe entries vs plan's ~289 → T1 reconciles | candleSnapshot endTime EXCLUSIVE |
| T1 harvest all dexes: funding + candles + snapshots | codex GPT5.6-High | DONE | f1387e4 | 67 tests GREEN; adv-review FIX-FIRST (false-completeness) → coverage audit reworked | 586k funding rows / 225 HIP-3 + BTC/ETH/SOL; **complete 105 / candle_truncated 78 / no_data 45** (data-bearing 183); candle shortfall = REAL inactivity (probed), not bug | T2–T7 join on per-series coverage, NOT universe membership |
| T2 S-A census + persistence + capacity map | codex GPT5.6-High | DONE | cffc2ea | 10 tests GREEN; adv-review SHIP + honesty fix | **0/183 carry-relevant** (real: half-life median 1.3h/max 9.9h ≪ 24h bar). tri-state carry {carry 0/measured_fail 169/insufficient 14}; 67 pass $1M floor | half-life≥24h bar structurally unreachable at hourly cadence → pre-registered OVERRIDE POINT; **T3 selects on liquidity floor NOT carry flag** |
| T3 S-C carry backtests + decomposition | codex GPT5.6-High | queued | — | — | — | — | none |
| T4 S-B oracle pull (G-F1 ≤$40 scope) + mechanics reconciliation | codex GPT5.6-High | DONE | 3fcafc5 | 14 tests GREEN; dual review (corr SHIP + adv FIX-FIRST tautology) → reframed, 2 fix passes | **$0 pull** (oracle on disk); feed-reconciliation R²=0.99 (raw premium 0.9957; up-to-13%-affine); intra-hour predictable vs iid null (R²@50m-lead=0.58, iid_excess +0.40) | **G-F2 → S-D keeps prediction framing** |
| — G-F2 decision | — | — | — | pre-registered F-B: observed R²@min50=0.962 ≥ 0.95 → **S-D (T5) FULL scope (prediction framing survives)** | caveat: raw 0.96@min50 partly partial-observation; long-lead predictability moderate not near-perfect | routed |
| T5 S-D funding-clock brackets (G-F2 routes scope) | codex GPT5.6-High | queued | — | — | — | — | none |
| T6 S-E cross-dex spreads + twin-basis risk | codex GPT5.6-High | queued | — | — | — | — | none |
| T7 S-F event-rate normalization + wallet bridge | codex GPT5.6-High | queued | — | — | — | — | none |
| T8 consolidated report + spend + close-out | codex GPT5.6-High | queued | — | — | — | — | none |

## Escalations / decisions log
- **G-F1 (T4 paid-pull gate):** oracle for SKHX/SMSN (S-B clean coins) already fully on disk from Study-2 T5 (498 hourly partitions each, 2026-06-17→07-08). Dry-run `files=0 cost=$0.00`. NO pull; S-B answered from on-disk data. Study-3 new spend = $0.
- **G-F2 (T4→T5 mechanics gate):** F-B pre-registered metric observed R²@min50 = **0.962 ≥ 0.95** → **S-D (T5) retains FULL scope incl. prediction framing.** Honest caveat carried: the raw 0.96@min50 is partly partial-observation (50/60 of averaging window seen); true long-lead predictability is moderate (R²=0.58 at a 50-min lead) but REAL (iid_excess +0.40 vs an iid null). T5 should frame funding-clock prediction as "moderate, strengthening through the hour," not near-perfect.
- **Review note (T4):** first adversarial pass caught the R²=0.99 headline as a feed-consistency tautology (raw premium alone scores higher) + a wrong-null shuffle control; corrected over 2 fix passes (feed-reconciliation relabel + iid null). Codex resume-queue failure on fix-2 (no work lost, tree intact) → re-dispatched fresh.

## Carried-over open items (from Studies 1–2, relevant here)
- SKU billing GB-vs-GiB + HL-feed SKU rates: still unreconciled vs console (MED) — T4's dry-run inherits the conservative Trades-tier pricing.
- Oracle feed inception (first partition 2026-06-17 16:00, unverified) — T4 should record what listing shows.
- `mkts` dex absent from flat files — if S-A shows mkts markets matter, flag; REST data for them is unaffected.
- Post-2026-06-18 CoinAPI quotes poisoned — binding rule §1.2.

## RESUME state
(not triggered)
