# HANDOFF — Overnight Studies 1 & 2 orchestration (2026-07-10)

You are **Opus, the orchestrator** running the **agentic-loop** skill for the plan
`docs/superpowers/plans/2026-07-09-overnight-studies-1-2.md`. You never read source or
write code yourself — you dispatch codex to implement and CE agents to review, hold only
`LEDGER.md` + small cards, and commit each task on branch `studies/overnight-2026-07-09`.

**On resume: read `LEDGER.md` FIRST (canonical state), then this file (mechanics).**

---

## Where things stand (2026-07-10 morning)

- **Study 1: COMPLETE & committed.** T0→T4. Commits: `cbda9c4` (T0 client+spend meter),
  `45ca33f`+`dcebcf5` (T1 pull, 16,763 files/$70.66), `e5100b5` (T2 loaders/book/calendars),
  `8d424a4` (T3 markout engine), `2f23378` (T4 run+report).
  - Result (numbers only, no verdict): net 30s passive-maker markout ≈ **−2 to −3 bps** across
    RTH/off-hrs/weekend; off-hours **not** robustly better than RTH → **leans against prior #1**.
    Report: `docs/reports/study1_offhours_markout_2026-07-09.md`.
- **Study 2: in progress.**
  - **T5 DONE & committed** (`b9b4e63`): cheap-data pull (L4 for 5 markets, oracle SKHX/SMSN/GOLD,
    full 20.75d HLSYSTEMEVENTS, funding for 225 markets) + A5 spend-meter SKU extension. +$15.82.
  - **T6 RUNNING** (codex job `task-mrf01sz8-a5e3zw`, monitor `b1myom2qt`): liquidation tagging +
    the **G2 decision** (does HLSYSTEMEVENTS record liquidation actions? if not → proxy-tagged
    fallback). TDD task. **Next action: pick up its card, review, commit.**
  - **T7 queued**: targeted L4 **book** pull for ±30min around each tagged event + matched
    baselines (dry-run costed first, ≤$40), then cascade anatomy + forced-flow markout.
    **Gets ce-correctness-reviewer** (money math). Use CoinAPI **concurrency 8 / 640 RPM**.
  - **T8 queued**: `docs/reports/study2_forced_flow_2026-07-09.md` + combined summary + final
    spend reconciliation + LEDGER close-out.

## Budget
- Spend meter (`data/spend.json`, flock-guarded): **$86.48**. Ceiling **$180**, G3 pre-download
  pause at **$178** (client-enforced). Balance ~$105. Remaining work (T7 targeted pull) is small.
- **Operator directive (durable): run autonomously to the cap — do NOT pause for per-purchase
  approval.** Only surface for a true blocker, plan-stale (G4), or hitting the cap.

---

## The loop (per task)
1. **(Optional) RESEARCH** via `Explore` (read-only) → SEAM-CARD, when wiring existing modules.
2. **IMPLEMENT** via `codex:codex-rescue` (Agent tool, `subagent_type: codex:codex-rescue`).
   Give it a bounded brief: task card + plan §-pointers, NOT the conversation. TDD tasks
   (T0/T2/T3/T6/T7) require strict RED→GREEN with **pasted real pytest lines**.
3. **REVIEW** via `compound-engineering:ce-adversarial-reviewer` (always) reading the working-tree
   diff fresh; **+ `ce-correctness-reviewer` on T3 and T7** (money math). Scope reviewers to the
   task's files; tell them to ignore git-ignored `data/`.
4. **TRIAGE**: fix BLOCKER/HIGH (+ cheap high-value MEDs that gate the next task); record other
   MED/LOW as ledger follow-ups (don't gold-plate). Max 2 fix passes → escalate.
5. **COMMIT** (you run git yourself — it doesn't bloat context): conventional-commit message,
   Co-Authored-By trailer, on branch `studies/overnight-2026-07-09`. Data stays git-ignored.
6. **LEDGER**: update the task row (status, SHA, verdict, follow-ups) and discard card bodies.

## How to drive codex (critical mechanics)
- `codex:codex-rescue` launches a **background codex job** and returns a job id like
  `task-<id>` + an agentId. It does NOT block.
- Job state lives at:
  `/home/jnitz/.claude/plugins/data/codex-openai-codex/state/charybdis-aeb83cd2d6a6ed19/jobs/<task-id>.json`
  Poll `.status` (`running`→`completed`); the final IMPL-CARD is in `.rendered` (or `.result.rawOutput`).
  Log: same path with `.log`.
- **Wait pattern**: arm a `Monitor` that polls the job JSON `.status` every ~25s and echoes on
  `completed`/`failed`; for long pulls add a heartbeat every ~10 min reading `data/spend.json`
  `running_cost_usd` + log tail. (Plain background-Bash `until` loops get reaped on long waits;
  Monitor survives better. Monitors time out at ≤3.6M ms — re-arm if needed by re-checking the
  job JSON directly.)
- To continue the SAME codex thread (e.g. recover a script it wrote), `SendMessage` to its agentId.
- Extract a card:
  `python3 -c "import json;print(json.load(open('<job>.json'))['rendered'])"`

## Config / environment facts
- **codex network is enabled** for its workspace-write sandbox (`~/.codex/config.toml` →
  `[sandbox_workspace_write] network_access = true`). Without it codex can't reach CoinAPI.
- codex's sandbox can't reach the user **systemd** manager → it substitutes `prlimit --as=6GiB`
  for the plan's `systemd-run MemoryMax=6G`. Functional-equivalent; accepted.
- **CoinAPI flat-files S3**: endpoint `s3.flatfiles.coinapi.io`, bucket `coinapi`, key =
  `COINAPI_API_KEY` from `.env`, secret literal `coinapi`, region us-east-1, SigV4.
  **Rate limits: Tier 3 = concurrency 8, 640 RPM** (raised from 4/160 overnight). Backoff on 429/403.
- Pricing confirmed **decimal-GB** (meter tracked actual within ~0.7% at the credit lockout).
- Tooling: `uv` (project env has polars/pyarrow/etc — base python does NOT; use `uv run`),
  codex-cli 0.144.1. Tests: `uv run pytest -q tests/<file>` (never the full tree casually).

## Open decisions / morning-override points (flagged for operator; none block)
- CI method = **cluster bootstrap** (market×6h block, 2000 reps, 95% pct); tunable.
- Staleness `max_quote_age_s=60`, `min_clusters=5` (null CI below) — tunable → T4 re-runs.
- Fee = **1.5bps maker, `assumed`** — verify vs official HL fee docs.
- HL feed SKUs (oracle/sysevents/twap) priced **assumed** at Trades tier — verify vs console billing.
- **CoinAPI auto-recharge is NOT firing** despite being enabled (operator tops up manually).
- Deferred LOW findings tracked in LEDGER "Deferred review findings" / "T4/T3/T2 handoff notes".

## Deliverables by end
1. `docs/reports/study1_offhours_markout_2026-07-09.md` ✅
2. `docs/reports/study2_forced_flow_2026-07-09.md` (T8, pending)
3. Parquet under `data/reports/` (git-ignored); raw pulls under `data/` (git-ignored)
4. `LEDGER.md` complete + spend reconciliation ≤$180
5. Follow-ups list (in LEDGER)
