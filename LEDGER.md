# LEDGER — Overnight Studies 1 & 2 (2026-07-09)

**Plan:** `docs/superpowers/plans/2026-07-09-overnight-studies-1-2.md` (read it first; §2 has all external facts pre-baked — do not re-discover)
**Protocol:** agentic-loop. Orchestrator (Opus) never reads source / writes code. Implementer: GPT5.6-High via `codex:codex-rescue`. Reviewer: `ce-adversarial-reviewer` every task; + `ce-correctness-reviewer` on T3, T7.
**Budget state:** $64 credits, auto-recharge on, ceiling $180 (pause line, G3 at $178 projected). Spend so far: ~$0.10 (exploration probes).

**Queue + next:** T0 → T1 → G1(PAUSE for operator billing check) → T2 → T3 → T4 ‖ T5(after G1) → T6(G2) → T7 → T8

| task | implementer | status | commit SHA | check | verdict | follow-ups | decision? |
|---|---|---|---|---|---|---|---|
| T0 scaffold + ffs3 client + spend meter | codex GPT5.6-High | DONE | (pending) | pytest 5/5 GREEN | LOW (A1/A2/A4 fixed; L1/L2 hygiene) | A3(GiB→G1) A5(unknown-SKU price→pre-T5) A6 A7 L1 L2 | none |
| T1 study-1 pull (≤$60) | codex GPT5.6-High | queued | — | — | — | mkts-gap check | G1 after |
| T2 loaders + calendars | codex GPT5.6-High | queued | — | — | — | — | none |
| T3 markout engine | codex GPT5.6-High | queued | — | — | — | fee bps `assumed` | none |
| T4 run + study-1 report | codex GPT5.6-High | queued | — | — | — | — | none |
| T5 study-2 cheap data (≤$45) | codex GPT5.6-High | queued | — | — | — | oracle GOLD wart demo | after G1 |
| T6 liquidation tagging | codex GPT5.6-High | queued | — | — | — | — | G2 |
| T7 event-window book pulls (≤$40) + anatomy | codex GPT5.6-High | queued | — | — | — | — | none |
| T8 study-2 report + close-out | codex GPT5.6-High | queued | — | — | — | — | none |

## Escalations / decisions log
- **2026-07-10 (pre-T0):** T0 codex run hit BLOCKER `curl (6) Could not resolve host` — codex's `workspace-write` sandbox disables network by default. Verified endpoint + creds work from a normal shell (free ListObjects returned valid XML). Operator authorized enabling network in codex config. Added `[sandbox_workspace_write] network_access = true` to `~/.codex/config.toml` (reversible). T0 re-dispatched. Codex correctly refused to fabricate the fixture on the failed run (good).

## Deferred review findings (tracked, not yet actioned)
- **A3 (MED, ffs3.py:20,26-27,182):** spend meter uses decimal GB (1e9). If CoinAPI bills per GiB (2^30), meter under-counts real spend ~7.4% (dangerous near ceiling). **Resolve at G1** (operator billing reconciliation after T1) — G1 must explicitly confirm GB vs GiB. Immaterial for T1 (~$60 est, far from $178).
- **A5 (MED, ffs3.py:247-259,279):** `sku_from_key` hard-aborts the whole manifest on any dataset outside {Order Book, Trades, Quotes}. **T5 needs T-HLORACLEPRICES / T-HLSYSTEMEVENTS / T-HLTWAPSTATUSES**, which aren't in the §0 price table. **Decision needed before T5:** how to price those SKUs (likely small; pick a conservative tier or get operator rate). Not blocking T1.
- **A6 (LOW, ffs3.py:355-360):** size-mismatch error path doesn't `record()` bytes before raising → meter under-counts on corrupt/partial transfer. Revisit if retries observed.
- **A7 (LOW, ffs3.py:335-343):** manifest pause is all-or-nothing; no partial pull to the line + no RESUME.md write, contra G3 text. Only bites if we approach $178 (not expected tonight). Revisit at G3/T8.
- **L1 (LOW, tests/test_ffs3.py:31-41):** A1 lost-update test is sequential — exercises the on-disk re-read but not flock mutual exclusion (a reverted flock w/ re-read kept would still pass). flock code inspected-correct. Add a truly concurrent (fork) test if revisiting the meter.
- **L2 (LOW, tests/fixtures/list_objects_trades_2026070900.xml):** orphaned after XML-parser removal. KEPT intentionally as a real captured ListObjects reference (documents live S3 schema for T1/T2). Delete if unused by end of run.

## RESUME state
(not triggered)
