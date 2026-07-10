# Overnight Plan — Study 1 (off-hours markout kill test) + Study 2 (SKHX liquidation forensics)

**Date:** 2026-07-09
**Status:** PLAN — ready for orchestrator handoff
**Orchestrator:** Opus, running the agentic-loop protocol (ledger + cards; orchestrator never reads source or writes code)
**Implementers:** GPT5.6-High via codex (`codex:codex-rescue` agent / `codex:rescue` skill) for all coding tasks
**Reviewers:** `compound-engineering:ce-adversarial-reviewer` on every task; add `ce-correctness-reviewer` on T3 and T7 (money math — silent errors are expensive)
**Researcher:** `Explore` for repo seams once code exists; the external facts are pre-baked in §2 — do not re-discover them
**Parent spec:** `docs/superpowers/specs/2026-07-04-hip3-market-evaluation-spec.md` (its design rules are binding)
**Priors:** `docs/2026-07-05-strategy-priors.md` (data adjudicates, not the story)

---

## 0. Mission and budget

Two research studies, both from **historical CoinAPI flat files** (no live capture, no order placement, no keys beyond the CoinAPI key in `.env`):

- **Study 1** — prior #1 kill test: is simulated passive maker markout on HIP-3 index perps visibly better off-hours/weekends than during RTH? Pre-registered falsification: if not, prior #1 is dead.
- **Study 2** — SKHX/SMSN forced-flow anatomy: identify liquidation-driven flow, measure cascade overshoot/reversion and passive-maker markout during forced flow vs baseline, conditioned on funding/OI/oracle regime.

**Budget:** $64 credits on account, auto-recharge active. **Spend ceiling $180 for tonight — a pause line, not a safety margin: run until projected spend reaches $178, then STOP downloads, finish all analyses on data in hand, and write resume state into the ledger (operator resumes tomorrow after recharge).** Estimated: Study 1 ≈ $85, Study 2 ≈ $70 with disciplined windows — likely fits, but prioritize spend in queue order so a pause hits Study 2's book pulls, never Study 1. Listing (ListObjects) is effectively free — always list and size **before** downloading.

**Pricing (pay-as-you-go, $1/credit, per GB downloaded, tiers reset per day per SKU; "SKU" = dataset type is the working assumption — see §4 gate G1):**

| dataset | first tier | mid | top |
|---|---|---|---|
| Order Book (LIMITBOOK_FULL) | $8/GB (first 1 GB/day) | $4/GB (next 9) | $2/GB (10+) |
| Trades | $24/GB (first 0.5 GB/day) | $12/GB (next 4.5) | $6/GB (5+) |
| Quotes | $8/GB (first 0.5 GB/day) | $4/GB (next 4.5) | $2/GB (5+) |

Batch same-SKU pulls into one session to ride tiers down. **Never** bulk-pull all HIP-3 L4 books (~1 TB ≈ $2k).

---

## 1. Non-negotiable design rules (from the parent spec — enforce in review)

1. **No look-ahead**: any normalization uses trailing windows only. Check every denominator.
2. **Executable quotes**: all economics vs time-aligned book/touch, never prints or mids alone.
3. **No tunable entry signal**: the sim measures venue economics, not a strategy. Zero fitted parameters.
4. **Memory caps**: every analysis command wrapped `systemd-run --user --scope -q -p MemoryMax=6G -p MemorySwapMax=0 uv run …` (6G solo; (available−1G)/N for N parallel). Column-projected reads only; never load a full day of book events wholesale.
5. **Disk discipline**: everything under `data/` (git-ignored); budget ≤25 GB total; keep files gzipped, decompress in stream.
6. **Cluster-robust CIs** by market × hour-block (e.g. 6h blocks). Both a point estimate and a CI or it doesn't go in the report.
7. **Null results are results.** Reports contain numbers + CIs, **no verdicts** — the operator decides.
8. **Timestamps**: files carry `time_exchange` and `time_coinapi`. Align on `time_exchange`; report the observed exchange→coinapi latency distribution once, as context.

---

## 2. Pre-baked facts (verified 2026-07-09 — do NOT re-derive; cite this section)

### 2.1 CoinAPI flat files S3 access

- Endpoint `https://s3.flatfiles.coinapi.io/`, bucket `coinapi`. S3-compatible, AWS SigV4.
- Credentials: access key = `COINAPI_API_KEY` from repo `.env`; secret = the literal string `coinapi`; region `us-east-1`.
- curl pattern (note **zsh eats `$VAR:c` — always brace**):
  `curl -s --user "${COINAPI_API_KEY}:coinapi" --aws-sigv4 "aws:amz:us-east-1:s3" -H "Accept: application/xml" "https://s3.flatfiles.coinapi.io/coinapi/?prefix=...&delimiter=/"`
- boto3 works too (endpoint_url + same creds). ListObjects V1 semantics; responses can list newest-first; `max-keys` applies to keys, not CommonPrefixes.
- Key format: `T-<TYPE>/D-<PARTITION>/E-<EXCHANGE>/IDDI-<n>+SC-<SYMBOL_ID>+S-<COIN>.csv.gz` (coin `:` encoded as `__003A`). HLSYSTEMEVENTS is one exchange-wide file: `T-HLSYSTEMEVENTS/D-<PART>/E-HYPERLIQUIDL4.csv.gz`.

### 2.2 The two coverage eras (both needed)

| era | exchange id | partitions | window | HIP-3 coverage |
|---|---|---|---|---|
| L2-normalized | `E-HYPERLIQUID` | daily `D-YYYYMMDD` | **2026-03-11 → 2026-06-08** | ~129–162 DPERP markets/day; trades, quotes, LIMITBOOK_FULL (level-aggregated events, no order ids) |
| L4 | `E-HYPERLIQUIDL4` | hourly `D-YYYYMMDDHH` | **~2026-05-08 → present**, lags ~1 day | DPERP trades (+`user_taker`/`user_maker`), quotes, LIMITBOOK_FULL (order-level: `order_id`, `user`, `tif` incl. `Alo`, `orig_size`, trigger fields), T-HLORACLEPRICES, T-HLSYSTEMEVENTS, T-HLTWAPSTATUSES |

- Symbol ids: `HYPERLIQUID_DPERP_<DEX>_<COIN>_USDC` (L2 era), `HYPERLIQUIDL4_DPERP_<DEX>_<COIN>_USDC` (L4 era).
- **May 8 → Jun 8 both eras overlap** → mandatory cross-validation window (different pipelines; diff trade counts/prices before trusting either).
- Post-2026-06-09, DPERP exists ONLY under `E-HYPERLIQUIDL4`.
- Known gap: `mkts` dex never observed in flat files — confirm via listing in T1 and record.

### 2.3 Observed schemas (headers pasted from real files)

- Trades (L2 era): `time_exchange;time_coinapi;guid;price;base_amount;taker_side;id_exch_guid;id_exch_int_inc;order_id_maker;order_id_taker`
- Trades (L4 era): same + `;user_taker;user_maker`
- LIMITBOOK_FULL (L2 era): `time_exchange;time_coinapi;update_type;is_buy;entry_px;entry_sx;order_id` (update_type SNAPSHOT + incrementals; times are time-of-day, no date — date comes from the partition; files can open with a prior-state SNAPSHOT)
- LIMITBOOK_FULL (L4 era): `…;order_id;user;tif;reduce_only;order_type;cloid;orig_size;trigger_condition;is_trigger;trigger_px;is_position_tpsl;children_oids;is_child;hl4_status`
- Quotes: `time_exchange;time_coinapi;ask_price;ask_size;bid_price;bid_size` (plus symbol id col in some eras — inspect first row)
- HLORACLEPRICES: `time_exchange;time_coinapi;coin_id;update_class;mark_px;mark_daily_px;oracle_px;oracle_daily_px;external_perp_px;external_perp_daily_px;spot_px_input;mark_px_input;external_perp_px_input`; `update_class ∈ {Deployer, Fallback}`. **WART:** files are keyed by bare coin (`S-GOLD`, `S-US500`) and interleave rows from *different dexes* sharing that coin name, with no dex column — disambiguate by price-level clustering against per-dex marks. Feed starts ~mid-June (exact start unverified).
- HLSYSTEMEVENTS: `time_exchange;time_coinapi;exchange_id;block_number;event_type;json_payload` — raw action stream; a sampled quiet hour showed only `order`/`cancelByCloid`/transfer actions; **liquidation action visibility is UNCONFIRMED** (gate G2).

### 2.4 Sizes actually measured (gzipped)

- All-DPERP per day, L2 era: books ~160 MB, quotes ~36 MB, trades ~20 MB.
- Index perps: ~2.6–4.3 MB/day/market books (km:US500 2.6, xyz:SP500 4.3); km:US500 Saturday = 2,933 trades.
- L4 books: xyz:XYZ100 ~21 MB/hour (fat), xyz:NVDA ~6.5 MB/hour, xyz:TSLA ~5.6 MB/hour. All-DPERP L4 books ≈ 750 MB/hour — **windowed pulls only**.
- Sample files from today live in the session scratchpad; treat as disposable — re-pull fixtures into `tests/fixtures/`.

### 2.5 Hyperliquid public REST (free, ≤1 req/s)

- `POST https://api.hyperliquid.xyz/info` — `{"type":"perpDexs"}`; `{"type":"metaAndAssetCtxs","dex":"<name>"}`; `{"type":"fundingHistory","coin":"xyz:SKHX","startTime":<ms>}` (≤500 rows/call, paginate by startTime).
- Funding is hourly; APR = rate × 24 × 365. Verified 21-day means: xyz:SKHX +72% APR (73% hrs positive, $483M OI), xyz:SMSN +46%, xyz:SMH +34%, xyz:SP500 +2.3%, km:US500 ≈ 0 (median 0), hyna:BTC +6.5%.

### 2.6 Market lists

- **Study 1 markets (8):** `xyz:SP500`, `km:US500`, `flx:USA500`, `cash:USA500`, `km:USTECH`, `xyz:XYZ100`, `flx:USA100`, `km:SMALL2000`.
- **Study 2 markets:** `xyz:SKHX`, `xyz:SMSN` (targets); `xyz:SMH`, `xyz:KR200`, `xyz:EWY` (hedge-leg references, trades+quotes only).
- Fee assumption: HL base perp tiers × dex `deployerFeeScale` (xyz/km/flx/cash = 1.0). Document actual base maker/taker bps from official HL fee docs in T3 and mark `assumed` — do not guess silently.

---

## 3. Pre-registered metrics (fixed BEFORE code; changing them requires operator sign-off)

### Study 1 — off-hours vs RTH markout
- **Fill rule (conservative):** simulated maker joins the touch at each L1 change; counted filled only when (a) a trade prints strictly through the joined price, or (b) prints at the price for cumulative size exceeding queue-ahead, where queue-ahead = displayed size at join (L2-era book events where available, else L1 size). State the upper-bound bias.
- **Markout:** vs microprice mid at **1s, 5s, 30s, 2m, 10m**; units **bps of notional**; **net of** maker fee and expected funding drift over the hold.
- **Primary decision number:** net markout at **30s**, both sides pooled, per market, segmented {RTH, off-hours weekday, weekend}. RTH per NYSE calendar (half-days handled; DST correct; ET↔UTC via zoneinfo).
- **Falsification (pre-registered in priors doc):** if weekend/off-hours net markout is not visibly better than RTH (CIs separating) across the index-perp set, prior #1 is dead.
- Secondary: by side, by hour-of-day, by filling-print size bucket (trickle vs sweep), spread/depth/uptime census per segment, era-overlap consistency check (May 8–Jun 8: same-market trade counts within ~5% and aligned prices between pipelines; report divergences).

### Study 2 — forced-flow anatomy (SKHX/SMSN)
- **Forced-print identification:** primary = liquidation actions in HLSYSTEMEVENTS (if present — gate G2); fallback = pre-registered heuristic: aggressor bursts ≥3× trailing 1h median trade rate AND price displacement ≥3× trailing 1h σ(1-min returns) within 60s, wallet-repeated market sells/buys via `user_taker`. If the fallback is used, every downstream table is labeled `proxy-tagged`.
- **Cascade anatomy per event:** depth consumed (levels × size), overshoot = max adverse excursion of microprice vs pre-event 1-min mean, reversion half-life (time to retrace 50% of overshoot), duration.
- **Primary decision number:** simulated passive-fill net markout (same fill rule and horizons as Study 1) **during forced-flow windows vs matched baseline windows** (same market, same hour-of-day, no event within ±30 min).
- Conditioning axes: funding state (trailing 24h mean APR bucket), OI (daily census), oracle regime (Korean session live vs frozen — KRX calendar; `update_class` Deployer vs Fallback frequency around events).
- No prediction model, no fitted trigger — anatomy only.

---

## 4. Decision gates (PAUSE and surface to operator)

- **G1 (after first paid pull, end of T1):** report bytes downloaded × list-price estimate; operator verifies console billing matches (settles the SKU ambiguity). Do not start Study 2 paid pulls before G1 clears.
- **G2 (T6):** if HLSYSTEMEVENTS shows no liquidation-like action type over ≥1 week of SKHX data, switch to the pre-registered fallback heuristic and label outputs `proxy-tagged`. This is a pre-authorized switch, not a re-plan — but report it.
- **G3 (any time):** projected total spend ≥ $178 → stop all downloads (do NOT abort analyses), complete every analysis task runnable on data already on disk, write a `RESUME.md` block into the ledger listing exactly which manifest files remain un-pulled and their $ estimate, and note truncation in any affected report. This is a scheduled pause, not a failure.
- **G4:** two consecutive tasks escalate → plan is stale, stop and re-plan with operator.

---

## 5. Task queue (agentic-loop; one row each in LEDGER.md)

Codex dispatch notes for the orchestrator: implement via `codex:codex-rescue` with explicit briefs; codex agents get the task card + §1/§2/§3 pointers, never the whole conversation. Reviewer is always a Claude CE agent reading the working-tree diff fresh. TDD applies to T0/T2/T3/T6/T7 (fixtures from small real downloaded slices committed under `tests/fixtures/`, a few hundred KB max).

| id | task | implementer | check (RED→GREEN) |
|---|---|---|---|
| **T0** | Scaffold: `uv` project (`pyproject.toml`; deps: httpx, boto3, polars, pyarrow, zstandard, exchange_calendars, pytest); `charybdis/ffs3.py` — flat-files client: SigV4 via boto3, list-with-sizes, manifest builder, downloader with **spend meter** (`data/spend.json`: bytes/SKU/day + $ estimate at §0 rates, pause-at-$178 per G3, `--dry-run` prints plan+cost and exits) | codex GPT5.6-High | pytest: listing parses real XML fixture; spend meter math; dry-run flags over-ceiling manifest as PAUSE |
| **T1** | Study 1 data pull: list → manifest (verify all 8 markets exist both eras; check `mkts` gap; record per-file sizes) → pull L2-era trades+quotes+books and L4-era trades+quotes for the 8 markets; L4 books **NOT** pulled yet. Emit `docs/reports/pull_study1_<date>.md` (files, GB, $ est). **→ G1 PAUSE** | codex GPT5.6-High | manifest row-count vs listing; spot re-download idempotent; spend.json updated; est ≤$60 |
| **T2** | Loaders + calendars: streaming CSV.gz → polars readers per schema (§2.3); book reconstructor for L2-era events (SNAPSHOT+incremental → L1/depth series); NYSE + KRX session labelers (DST-correct, half-days); segment labels {RTH, off-hrs weekday, weekend, holiday} | codex GPT5.6-High | pytest on fixtures: book reconstruction matches hand-computed L1 at 3 points incl. across a SNAPSHOT; calendar edge cases (2026-03-08 DST, Jul 3 half-day, KRX holiday) |
| **T3** | Markout engine per §3 exactly; fee/funding netting (HL fee docs lookup, recorded `assumed`); cluster-robust CIs (market × 6h block); outputs one parquet + summary tables. **2nd reviewer: ce-correctness-reviewer** | codex GPT5.6-High | pytest: hand-built 20-tick fixture where fills & markouts are computable on paper; no-lookahead test (shuffling future rows changes nothing before t) |
| **T4** | Run Study 1 (systemd-run wrapped) over full data; era-overlap cross-validation; write `docs/reports/study1_offhours_markout_2026-07-09.md` — census table, markout tables w/ CIs per segment/market/horizon, falsification line stated numerically, biases/assumptions section, **no verdicts** | codex GPT5.6-High | report renders; every number has n + CI; overlap check table present |
| **T5** | Study 2 cheap data: full funding history (REST, paginated, all HIP-3 + the 5 markets), oracle files ~Jun 17→present for SKHX/SMSN coins (+GOLD as wart test-case), HLSYSTEMEVENTS 3 recent weeks, L4 trades+quotes for the 5 Study-2 markets (May 8→present). Emit pull report + spend update | codex GPT5.6-High | spend ≤$45 for this task; funding series continuous (no >2h gaps unexplained); oracle dex-disambiguation demo on GOLD |
| **T6** | Liquidation tagging per §3: scan system events for liq actions (**→ G2 decision**); implement chosen path; tag SKHX/SMSN trade tape; event table parquet | codex GPT5.6-High | pytest: heuristic fires on synthetic burst fixture, silent on calm fixture; event table has ≥1 real event or documented absence |
| **T7** | Targeted L4 book pulls for tagged event windows ±30min + matched baselines (budget ≤$40, listed & dry-run costed first); cascade anatomy + forced-flow markout per §3; conditioning tables. **2nd reviewer: ce-correctness-reviewer** | codex GPT5.6-High | pytest: anatomy metrics on synthetic cascade fixture; spend gate respected |
| **T8** | `docs/reports/study2_forced_flow_2026-07-09.md` (same standards as T4) + one-page combined summary + final spend accounting + LEDGER close-out | codex GPT5.6-High | reports render; spend table reconciles with spend.json |

Ordering: T0→T1→(G1)→T2→T3→T4 completes Study 1. T5 may start in parallel with T2 (it's cheap-data only) **after G1 clears**. T6→T7→T8 sequential.

## 6. Escalation & abort (from the loop protocol)

Fix-until-clean max 2 passes → escalate. IMPL-CARD without a pasted RED line → reject, re-dispatch. Subagent runs the full test tree or OOMs → abort task, report. Anything touching order placement, wallets, or keys beyond reading `COINAPI_API_KEY` → hard abort (research-only repo).

## 7. Deliverables by morning

1. `docs/reports/study1_offhours_markout_2026-07-09.md` — the prior-#1 falsification table.
2. `docs/reports/study2_forced_flow_2026-07-09.md` — cascade anatomy + forced-flow markout (possibly `proxy-tagged`).
3. Parquet outputs under `data/reports/`; raw pulls under `data/capture-hist/` (git-ignored).
4. `LEDGER.md` complete; spend accounting ≤$180 with receipts-level detail.
5. Follow-ups list (MED/LOW review findings, mkts gap, oracle-start-date, SKU billing verdict).
