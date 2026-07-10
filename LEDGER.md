# LEDGER — Overnight Studies 1 & 2 (2026-07-09)

**Plan:** `docs/superpowers/plans/2026-07-09-overnight-studies-1-2.md` (read it first; §2 has all external facts pre-baked — do not re-discover)
**Protocol:** agentic-loop. Orchestrator (Opus) never reads source / writes code. Implementer: GPT5.6-High via `codex:codex-rescue`. Reviewer: `ce-adversarial-reviewer` every task; + `ce-correctness-reviewer` on T3, T7.
**Budget state:** $64 credits, auto-recharge on, ceiling $180 (pause line, G3 at $178 projected). Spend so far: ~$0.10 (exploration probes).

**CoinAPI limits (operator-confirmed):** max concurrency **4**, **160 RPM** (~2.6 req/s), backoff on 429. Put these in every T5/T7 pull brief.

**Operating mode (operator directive 2026-07-10):** RUN AUTONOMOUSLY TO THE CAP. Do NOT pause for per-purchase approval. Hard guardrail = $180 ceiling / $178 G3 pre-download pause (client-enforced). G1 downgraded from blocking pause → non-blocking checkpoint (log spend + flag GB-vs-GiB for morning). Only surface to operator for a true blocker, plan-stale (G4), or hitting the cap.

**Queue + next:** T0✓ → T1(pull authorized, executing) → [G1 non-blocking] → T2 → T3 → T4 ‖ T5 → T6(G2 auto-switch) → T7 → T8

| task | implementer | status | commit SHA | check | verdict | follow-ups | decision? |
|---|---|---|---|---|---|---|---|
| T0 scaffold + ffs3 client + spend meter | codex GPT5.6-High | DONE | cbda9c4 | pytest 5/5 GREEN | LOW (A1/A2/A4 fixed; L1/L2 hygiene) | A3(GiB→G1) A5(unknown-SKU price→pre-T5) A6 A7 L1 L2 | none |
| T1 study-1 pull | codex GPT5.6-High | DONE-PARTIAL | (pending) | manifest 11,828/16,763; idempotence 3/3; spend $64.42 | done-check met; credit lockout | 4,935 L4-trade files unpulled ($6.24) resume when credits back | G1 ~settled (see below) |
| T2 loaders + calendars | codex GPT5.6-High | queued | — | — | — | — | none |
| T3 markout engine | codex GPT5.6-High | queued | — | — | — | fee bps `assumed` | none |
| T4 run + study-1 report | codex GPT5.6-High | queued | — | — | — | — | none |
| T5 study-2 cheap data (≤$45) | codex GPT5.6-High | queued | — | — | — | oracle GOLD wart demo | after G1 |
| T6 liquidation tagging | codex GPT5.6-High | queued | — | — | — | — | G2 |
| T7 event-window book pulls (≤$40) + anatomy | codex GPT5.6-High | queued | — | — | — | — | none |
| T8 study-2 report + close-out | codex GPT5.6-High | queued | — | — | — | — | none |

## Escalations / decisions log
- **2026-07-10 (T1 credit lockout — NOT the $178 cap):** T1-exec pulled 11,828/16,763 files (9.9 GB, meter **$64.42**) then hit a **CoinAPI 403 credit-quota lockout** — the $64 account balance (§0) exhausted; auto-recharge did NOT fire during the run. L2 era COMPLETE (books/trades/quotes 694 each); L4 quotes complete (7,890); **L4 trades only 1,856/6,791** — remainder is the 4,935 unpulled small files. Resume state: `data/study1_resume.json` (4,935 files, 0.52 GB, ~$6.24). Idempotence 3/3 passed. **Decision (autonomous):** proceed to build T2/T3 pipeline on the complete L2 data (sufficient for the primary off-hours-vs-RTH test); retry the $6 resume opportunistically before T4; T4 report labels L4 truncation + degraded era-overlap cross-val. NOT waking operator (credit/infra, not a purchase approval). **Morning action: confirm CoinAPI auto-recharge / add credits, then rerun `data/study1_manifest.json` (skips on-disk, pulls the 4,935).**
- **2026-07-10 (G1 / A3 ~settled favorably):** lockout fired at meter **$64.42** vs known **$64** balance → estimate within ~0.7% of actual ⇒ pricing is **decimal-GB, not GiB** (A3 resolved in the safe direction). Meter is trustworthy for the rest of the run. Operator should still eyeball console billing in the morning, but the auto-pause math is sound.
- **2026-07-10 (G1/T1 cost gate):** T1 free discovery built full manifest (16,763 files / 10.42 GB, all 8 markets both eras, mkts absent). Dry-run = **$70.66** (OB $24.59 / Trades $31.46 / Quotes $14.61), tripped my $65 pre-pull gate. Operator authorized full pull + directive to run autonomously to the cap (no per-purchase approvals). Proceeding to execute the saved manifest; client enforces $178 stop. **G1 billing/GB-vs-GiB reconciliation deferred to morning (non-blocking).**
- **2026-07-10 (pre-T0):** T0 codex run hit BLOCKER `curl (6) Could not resolve host` — codex's `workspace-write` sandbox disables network by default. Verified endpoint + creds work from a normal shell (free ListObjects returned valid XML). Operator authorized enabling network in codex config. Added `[sandbox_workspace_write] network_access = true` to `~/.codex/config.toml` (reversible). T0 re-dispatched. Codex correctly refused to fabricate the fixture on the failed run (good).

## Deferred review findings (tracked, not yet actioned)
- **A3 (MED, ffs3.py:20,26-27,182):** spend meter uses decimal GB (1e9). If CoinAPI bills per GiB (2^30), meter under-counts real spend ~7.4% (dangerous near ceiling). **Resolve at G1** (operator billing reconciliation after T1) — G1 must explicitly confirm GB vs GiB. Immaterial for T1 (~$60 est, far from $178).
- **A5 (MED, ffs3.py:247-259,279):** `sku_from_key` hard-aborts the whole manifest on any dataset outside {Order Book, Trades, Quotes}. **T5 needs T-HLORACLEPRICES / T-HLSYSTEMEVENTS / T-HLTWAPSTATUSES**, which aren't in the §0 price table. **Decision needed before T5:** how to price those SKUs (likely small; pick a conservative tier or get operator rate). Not blocking T1.
- **A6 (LOW, ffs3.py:355-360):** size-mismatch error path doesn't `record()` bytes before raising → meter under-counts on corrupt/partial transfer. Revisit if retries observed.
- **A7 (LOW, ffs3.py:335-343):** manifest pause is all-or-nothing; no partial pull to the line + no RESUME.md write, contra G3 text. Only bites if we approach $178 (not expected tonight). Revisit at G3/T8.
- **L1 (LOW, tests/test_ffs3.py:31-41):** A1 lost-update test is sequential — exercises the on-disk re-read but not flock mutual exclusion (a reverted flock w/ re-read kept would still pass). flock code inspected-correct. Add a truly concurrent (fork) test if revisiting the meter.
- **L2 (LOW, tests/fixtures/list_objects_trades_2026070900.xml):** orphaned after XML-parser removal. KEPT intentionally as a real captured ListObjects reference (documents live S3 schema for T1/T2). Delete if unused by end of run.

## Schema corrections (trust the file, not the doc — design rule §1)
- **Quotes header (verified on disk, differs from plan §2.3):** real L2-era Quotes = `id_site_coinapi;time_exchange;time_coinapi;ask_px;ask_sx;bid_px;bid_sx` (leading id col; `ask_px/ask_sx/bid_px/bid_sx` not `ask_price/ask_size`; `time_exchange` is full ISO). T2 loaders parse by actual header. Resolved by orchestrator (plan §2.3 itself says "inspect first row"); no operator needed. Confirm L4-era quotes header when those files land.
- T2 SEAM-CARD held by orchestrator: ffs3.py has NO csv/gzip/polars code → T2 builds loaders fresh; reuse only `sku_from_key:269`, `_destination_for:334`, dataclasses `ObjectInfo/ManifestFile/Manifest`. New modules: `charybdis/loaders.py`, `charybdis/book.py`, `charybdis/calendars.py`.

## RESUME state
(not triggered)
