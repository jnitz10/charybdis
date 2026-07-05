# Charybdis — HIP-3 Market Evaluation Spec (Phase A: research only)

**Date:** 2026-07-04
**Status:** SPEC — awaiting plan (writing-plans) → SDD delegation (opus implementers)
**Repo:** `~/Documents/trading/charybdis` (this repo; fresh — init + .gitignore only)
**Operator goal:** determine whether any Hyperliquid HIP-3 builder-deployed perp
market offers a maker edge that clears all-in costs, with evidence quality
matching the sortilex standard (executable quotes, clustered CIs, no look-ahead,
OOS discipline). MM is the preferred strategy class but the data must not
presuppose it.

---

## 1. Scope

### In scope (Phase A)
- Public read-only data collection from Hyperliquid REST/WS (no auth, no keys).
- Daily census of all HIP-3 dexes/markets; continuous capture of a shortlist.
- Analysis studies: market structure, simulated passive-fill markout, oracle
  forensics, fee/funding accounting, hedgeability classification.
- A decision memo with numbers + CIs per market. **No verdicts** — operator
  decides dead/alive.

### Explicit non-goals (Phase A)
- **No order placement, no wallet code, no private keys, no bridging.** There
  is no code path in this repo that can sign or submit anything.
- No ToS/geoblock circumvention tooling. The access/legal question is the
  operator's, deferred until Phase A produces a candidate worth the question.
- No strategy backtest beyond passive-fill markout simulation. Phase B (paper
  or live pilot) gets its own spec only if Phase A finds candidates.

### Success criterion for Phase A
After ≥7 days of shortlist capture, a memo answers per market:
1. Is there real two-sided flow? (volume, trade count, book uptime)
2. Simulated maker markout net of fees, in **bps of notional**, with
   cluster-robust CI. (Units are bps here, not ¢/contract — that's Kalshi.)
3. Oracle risk grade (update cadence, divergence behavior, off-hours regime).
4. Hedgeability class (liquid / partial / none).
5. Null result is a valid result and gets written up the same way.

---

## 2. Grounding: live HIP-3 landscape (snapshot 2026-07-04)

`POST https://api.hyperliquid.xyz/info {"type":"perpDexs"}` returns 10 entries;
first is `null` (main dex). The 9 builder dexes:

| dex | fullName | assets | character | notes |
|---|---|---|---|---|
| `xyz` | XYZ | ~98 | equities, commodities, FX, indices (AAPL…NVDA, GOLD, CL, SP500, VIX, DXY) | largest; OI caps to $1B; funding mult 0.5 everywhere |
| `flx` | Felix Exchange | 15 | equities + commodities + XMR | has dedicated oracleUpdater |
| `vntl` | Ventuals | 15 | **pre-IPO** (ANTHROPIC, OPENAI, SPACEX) + sector baskets | funding mult 0 on most — pure oracle-mark game |
| `hyna` | HyENA | 24 | crypto majors (BTC, ETH, SOL…) | **deployerFeeScale 0.1111** (others 1.0) — cheapest; overlaps main dex 1:1 |
| `km` | Markets by Kinetiq | 22 | equities/indices | tiny OI caps ($20k–$1.3M) |
| `mkts` | Markets By Kinetiq | 2 | US500, USTECH | newer sibling of km |
| `cash` | dreamcash | 15 | equities | |
| `para` | Paragon | 4 | AVGO, BTCD (dominance), TOTAL2, OTHERS | crypto-index flavored |
| `abcd` | ABCDEx | 0 | empty shell | ignore |

Structural gifts to exploit (free, no external data):
- **Cross-dex same-underlying pairs**: NVDA on xyz/flx/km/cash; GOLD on
  xyz/flx/vntl(GOLDJM)/hyna/km/cash; TSLA, SP500-equivalents, SILVER, OIL
  similar. Independent deployers, independent oracles, same underlying →
  oracle quality and mark divergence measurable by pure cross-section.
- **hyna vs main dex**: same chain, same asset (BTC, ETH…), different book +
  oracle + fee scale. Natural experiment for "what does a HIP-3 book cost you
  vs the real one."

Key API surface (verify exact shapes in task 1; all public):
- REST `info`: `perpDexs`; `meta` / `metaAndAssetCtxs` with `{"dex": "<name>"}`
  → per-asset `markPx, oraclePx, midPx, impactPxs, funding, openInterest,
  dayNtlVlm, premium` + margin tables, OI caps, growth modes.
- WS `wss://api.hyperliquid.xyz/ws`: `l2Book`, `trades`, `bbo`,
  `activeAssetCtx` — coin key for builder assets is namespaced `"dex:COIN"`
  (e.g. `"xyz:NVDA"`). **Confirming this works on WS is the first acceptance
  test of the capture task; if it fails, everything above it re-plans.**
- Fee schedule: base HL perp tiers × dex `deployerFeeScale`; deployer share up
  to 50%. Get the actual numbers programmatically (`userFees` needs an address,
  so instead document from `perpDexs` + public fee docs; record assumption).

### Reference implementation (pattern source, do not import)
`sortilex/scripts/capture/hl_l2_capture.py` (253 lines): WS l2Book+trades →
tagged JSONL (`{"recv_ms", "channel", "coin", "data"}`), one file/day, gzip on
rotation, heartbeat + watchdog + hourly reporter, clean SIGTERM. ~40MB/day for
10 main-dex alts. Copy the shape; charybdis is self-contained (no sortilex
imports).

---

## 3. Architecture

```
charybdis/
├── pyproject.toml            # uv project; deps: websockets, httpx, polars/pyarrow, zstandard
├── charybdis/
│   ├── api.py                # thin REST info client (rate-limited, retry)
│   ├── census.py             # Phase 0: snapshot + screen
│   ├── capture.py            # Phase 1: WS capture daemon
│   └── studies/              # Phase 3: one module per study
│       ├── structure.py
│       ├── markout.py
│       ├── oracle.py
│       └── costs.py
├── scripts/                  # thin CLI entrypoints (uv run python scripts/…)
├── data/                     # git-ignored
│   ├── census/               # parquet, one file per snapshot
│   ├── capture/<UTC-date>/   # hourly-rotated zstd JSONL per market-group
│   └── reports/
├── docs/
│   ├── superpowers/specs|plans/
│   └── reports/              # human-readable outputs (committed)
└── tests/
```

Design rules (carried from sortilex lessons — treat as global constraints):
- **Disk discipline from day 1** (the data/compact lesson): hourly rotation,
  zstd on close, bare `.jsonl` = in-progress / compressed = closed (mirror
  rule), single writer per directory, measured MB/day in the log, and a
  written archive policy before first byte. Budget: ≤2GB/day total.
- **Observable jobs**: unbuffered logging to a logfile, per-hour progress
  lines (msgs received, MB written, gaps), ETAs measured or "unknown".
- **Memory caps**: every analysis command wrapped
  `systemd-run --user --scope -q -p MemoryMax=<cap> -p MemorySwapMax=0 uv run …`
  (6G solo; (available−1G)/N for N parallel). Column-projected reads only;
  never load a day of L2 wholesale.
- **No look-ahead**: any normalization (vol, spread z, activity) uses trailing
  windows only. Check the denominator.
- **Executable quotes**: all economics vs time-aligned book levels, never
  prints/mids alone.
- Timestamps: wall-clock `recv_ms` on every line alongside exchange ts.

---

## 4. Phases

### Phase 0 — Census (REST only; first working code)

`scripts/census_snapshot.py`:
- Pull `perpDexs`, then `metaAndAssetCtxs` per dex (~10 requests total, ≤1/s).
- Emit one parquet: row = (snapshot_utc, dex, coin, markPx, oraclePx, midPx,
  impactPxs, funding, funding_multiplier, openInterest, oi_cap, dayNtlVlm,
  maxLeverage, marginMode, growthMode, deployerFeeScale, isDelisted).
- Emit `docs/reports/census_<date>.md`: dexes ranked, top-30 assets by
  dayNtlVlm, cross-dex same-underlying table, and a proposed capture shortlist.
- Cron: 1×/day full snapshot + optionally hourly light snapshot (ctxs only)
  once stable. Idempotent, <60s wall, exits nonzero on partial failure.

**Acceptance:** two snapshots 24h apart load into one dataframe; report renders;
shortlist proposal present. No screen thresholds hardcoded as "dead" — report
ranks, operator picks.

### Phase 1 — WS capture daemon

`scripts/capture_hip3.py --markets <file|list> --out data/capture`:
- Config-file-driven market list (start: shortlist from Phase 0; expected ~12–20
  markets spanning: 3–4 xyz large-caps, xyz GOLD + one energy, hyna BTC + ETH,
  **matching main-dex coins for the hyna pairs**, vntl OPENAI/SPACEX/ANTHROPIC,
  km:US500 or mkts:US500, one cash + one flx overlap name for the cross-dex set).
- Channels per market: `l2Book` (default depth), `trades`, `bbo`,
  `activeAssetCtx` (mark/oracle/funding stream — this is the oracle forensics
  feed; verify channel name/shape for builder dexes in task 1).
- Storage: per the disk rules above; JSONL schema identical to the sortilex
  capture (`recv_ms`, `channel`, `coin`, `data` raw) so analysis tooling stays
  simple and raw payloads survive schema surprises.
- Robustness: auto-reconnect w/ backoff, subscription re-establishment, ping
  heartbeat, watchdog restart on silence >60s, gap records written to the
  stream (`{"channel":"_gap", …}`), SIGTERM = flush + close + compress.
- Runs in tmux (command-bound), `tee -a` to logfile like existing captures.

**Acceptance:** 24h soak on the shortlist: zero unhandled exceptions, measured
MB/day within budget, gaps logged and totaling <1% of wall time, one
end-to-end line-count sanity check vs the hourly reporter's counters.

### Phase 2 — Reference-price layer (cheap first, external later)

2a (free, do first): cross-dex + main-dex references from data we already
capture — hyna:BTC vs main BTC (extend capture with the matching main-dex
coins), xyz:NVDA vs km:NVDA vs cash:NVDA, GOLD across 4+ dexes. No new infra;
this is a market-list decision in Phase 1.

2b (deferred decision): external equity/commodity reference (Polygon, IEX,
delayed RTH bars). Only if oracle forensics on 2a proves insufficient.
**Do not build in Phase A without operator sign-off.**

### Phase 3 — Studies (each pre-registers its metrics in the plan before code)

3.1 **Market structure census** (per market, per hour-of-day):
time-weighted spread (bps), depth at touch and within ±5/±10 bps, book uptime
(both sides quoted), quote update rate, trade count/size distribution,
% volume in RTH vs off-hours (equity names). Output: one parquet + md report.

3.2 **Passive-fill markout simulation** (the decision number):
- Simulated maker order joins the touch at observed L1; fill rule is
  conservative: filled only when a trade prints **through** our price, or at
  our price for size exceeding displayed queue ahead at join (queue estimated
  from L2 sizes at join, consumed by subsequent prints — an upper bound on
  queue ahead, state the bias).
- Markout at 1s / 5s / 30s / 2m / 10m vs microprice mid, in bps of notional,
  **net of** maker fee (dex-adjusted) and expected funding drift over the hold.
- CIs cluster-robust by market × hour block. Both sides, by hour-of-day, by
  trade-size bucket of the filling print (trickle vs sweep — the KXBTC15M
  lesson travels).
- No claims from in-sample tuning: the sim has no tunable entry signal in
  Phase A — it measures the venue's raw touch economics, not a strategy.

3.3 **Oracle forensics**:
oracle update cadence and step-size distribution per dex; mark−oracle spread
dynamics; cross-dex divergence for same-underlying (lead/lag, who reprices
first, magnitude of disagreement in volatile minutes); equity names off-hours:
does the book keep trading against a frozen oracle, and what happens to spreads
at the 09:30 ET unfreeze. Flag any market whose oracle behavior would shred a
resting maker (slow, coarse, or gameable) — with numbers, not adjectives.

3.4 **All-in cost card** (per market): maker/taker fee after deployerFeeScale,
funding multiplier × typical premium, margin tier / max leverage, OI cap
headroom vs observed OI. One table; inputs to 3.2's "net" line.

3.5 **Hedgeability classification** (mostly manual, data-assisted):
liquid-hedge (main-dex perp or deep spot exists: hyna names, xyz crypto),
partial (correlated proxy: sector baskets, SP500-alikes), none (vntl pre-IPO).
Note per class what strategy family is even eligible (hedged MM vs
inventory-holding MM vs stat-arb cross-dex).

### Phase 3 output — Decision memo
`docs/reports/phaseA_memo_<date>.md`: per shortlisted market one block —
flow reality, markout table w/ CIs, oracle grade, cost card, hedge class,
sample sizes and what's untested. Numbers and CIs only; operator decides.

---

## 5. Risks and open questions (carry into the plan as early tasks)

1. **WS namespacing for builder dexes** — `"dex:COIN"` on l2Book/trades is
   assumed from info-endpoint conventions; verify first, everything depends
   on it. (Fallback: asset-id addressing `@<index>` with per-dex offset
   10000×dex_index — documented HL convention, verify.)
2. **WS subscription limits** — ~20 markets × 4 channels = ~80 subs on one
   conn; HL allows far more, but confirm and shard connections if needed.
3. **`activeAssetCtx` availability for builder dexes** — if the oracle stream
   isn't available per-asset on WS, fall back to 1s REST polling of
   `metaAndAssetCtxs` per dex (cheap: one request covers the whole dex).
4. **vntl marks are model-driven** (no external truth, funding 0): markout vs
   microprice is still well-defined, but interpretation differs — flag in memo.
5. **Equity market halts/weekends**: capture runs 24/7; studies must segment
   by underlying-market-open regime, not assume continuous truth.
6. **Volume figures are self-reported by deployer-run infra** in ctxs; where
   possible cross-check dayNtlVlm against summed trade prints from our own
   capture (wash-trading smell test — new-venue hygiene).
7. **Fee schedule precision**: exact builder-dex fee formula (base tier ×
   scale, deployer cut) documented from official docs at plan time; record
   the assumption in the cost card and mark it `assumed` until verified
   against a real fill (Phase B).

## 6. Handoff

- Next step: `writing-plans` on this spec → `docs/superpowers/plans/`.
- Execution: subagent-driven-development; **opus implementers** (never inherit
  fable), sonnet acceptable for mechanical transcription tasks; adversarial
  review (opus) after each phase; parallel agents never commit.
- Task 1 of the plan must be the API-shape verification spike (risks 1–3):
  ~an hour of throwaway code before any real build.
- The operator's usage-allocation rule: fable plans and reviews; agents code.
