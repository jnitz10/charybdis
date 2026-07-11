# LEDGER — Study 4: Cross-Dex Oracle-Lag Taking (2026-07-10)

**Plan:** `docs/superpowers/plans/2026-07-10-oracle-lag.md` (read first; §2 pre-verified, §3 pre-registered — do not re-discover or re-litigate)
**Prior ledgers:** `docs/ledgers/2026-07-09-studies-1-2-LEDGER.md`, `docs/ledgers/2026-07-10-study3-LEDGER.md`. Program state: priors #1, forced-flow, and all funding angles killed/null; this study adjudicates prior #3 (oracle-lag taking). Remaining after this: hyna autopsy (prior #2).
**Protocol:** agentic-loop. Orchestrator (Opus) never reads source / writes code. Implementer: GPT5.6-High via `codex:codex-rescue`. Reviewer: `ce-adversarial-reviewer` every task; + `ce-correctness-reviewer` on T2, T5.
**Budget state:** cumulative meter $116.92. Study-4 ceiling **$60, pause at $58 projected**. T0–T4 are $0 (all on-disk); T5 is the ONLY paid task and is DOUBLE-gated: G-O1 results gate (S4-B must show a live cell at δ≥250ms) + dry-run ≤$45. CoinAPI balance ≈ $75 UNVERIFIED; auto-recharge KNOWN BROKEN → 403 lockout = resume manifest + continue free tasks.
**Operating mode:** autonomous to the cap (standing directive). Surface only for true blockers, G-O2 plan-stale, or the pause line.

**Critical new design rule (plan §1.1):** same-chain block quantization — cross-market same-timestamp events are UNORDERED; signals must strictly precede execution; drop-and-count same-timestamp cases. T0 measures actual timestamp granularity before anything trusts sub-second leads.

**Queue + next:** T0 → [T1 ‖ T4] → T2(G-O3) → T3 → G-O1 → [T5 | skip] → T6

| task | implementer | status | commit SHA | check | verdict | follow-ups | decision? |
|---|---|---|---|---|---|---|---|
| T0 scaffold: twin registry, signal lib, fee doc-check, block-quantization census | codex GPT5.6-High | queued | — | — | — | — | none |
| T1 S4-A twin lead/lag + stale-episode census | codex GPT5.6-High | queued | — | — | — | — | none |
| T2 S4-B conditional taker backtest (G-O3 maker-mode regression first) | codex GPT5.6-High | queued | — | — | — | — | none |
| T3 S4-C sniper census + residual curve | codex GPT5.6-High | queued | — | — | — | — | none |
| T4 S4-D oracle forensics + GOLD disambiguation prototype | codex GPT5.6-High | queued | — | — | — | — | none |
| G-O1 results + budget gate → T5 or skip | orchestrator | pending | — | — | — | — | criteria in plan §4 |
| T5 paid NVDA+GOLD twin expansion (dry-run ≤$45) | codex GPT5.6-High | queued (gated) | — | — | — | — | G-O1 |
| T6 consolidated report + spend + close-out | codex GPT5.6-High | queued | — | — | — | — | none |

## Escalations / decisions log
(empty)

## Carried-over open items (relevant here)
- Post-2026-06-18 CoinAPI quotes AND books poisoned — binding rule §1.2; usable book windows: L2 era 03-11→06-08, L4 era 05-08→06-18.
- Oracle bare-coin collision wart — S4-D(d) prototypes the fix on on-disk GOLD; blocks any future multi-dex oracle pull until solved.
- `mkts` dex absent from flat files (REST-only twins mkts:US500 / mkts:USTECH excluded from book studies).
- Taker fees `assumed` 4.5 bps × deployer scale pending T0 doc-check; fee table single-source at `data/reports/study3_fee_table.parquet`.
- SKU billing GB-vs-GiB unreconciled (MED); auto-recharge support ticket outstanding; flx feed-sparsity caveat (22–25% L2/L4 agreement) attaches to all flx cells.

## RESUME state
(not triggered)
