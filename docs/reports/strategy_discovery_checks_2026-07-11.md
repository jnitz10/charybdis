# Discovery-round validation checks: exhaustion reversal

**Date:** 2026-07-11
**Subject:** Three checks on the lead candidate in `strategy_discovery_2026-07-11.md`
(post-listing three-day exhaustion reversal): survivorship, real spread costs,
and oracle-basis decomposition. All from on-disk data, $0 spend.

**Scripts:** `scripts/2026-07-11-discovery-checks/` — `check_events.py`,
`check_survivorship.py`, `check_spreads.py`, `check_oracle_split.py`.
**Artifacts:** `data/reports/disc_check_{events,spreads,oracle}.parquet`.

## Event-set reproduction

The frozen rule reproduces the report within rounding (differences consistent
with the omitted funding term, avg +2.1bp/event):

| Variant | Report | Reproduction |
|---|---|---|
| Long events / trade-days | 217 / 78 | 214 / 78 |
| Long mean, day-clustered | +136.9bp t=2.41 | +134.7bp t=2.36 |
| Both sides | +146.6bp t=3.54 (409 ev) | +142.9bp t=3.43 (409 ev) |
| Top-1 daily | +137.9bp t=2.57 | +134.5bp t=2.49 (126 ev) |

## Check 1 — Survivorship: largely cleared

The candle panel is **not** survivor-only. Of 179 HIP-3 markets, 66 stopped
printing before 2026-07-07 and are present in the panel with truncated
histories. Every death is a **whole-dex shutdown**, not an individual
delisting: km (22 markets, Jun 10–17), flx (15, Jun 18–20), vntl (13, Jun),
cash (15, Jun 30–Jul 2). The harvest probe list itself contains dead markets
(km:RTX, vntl:OPENAI), confirming enumeration included non-surviving contracts.

- **Zero individual xyz delistings** in six months; all 86 xyz markets alive.
- 45 of 214 long events sit on markets that later died — all deaths came
  **>21 days after** the event, and those events returned +158.5bp vs +149.2bp
  on survivors. No "fell 8% then got delisted" losing tail exists in-panel.
- Silent dropouts are negligible: 2 signals lacked an entry candle, 3 lacked a
  24h exit — all three exits missing only because the sample ends (signals of
  2026-07-09). Marked to last close those three were −468 to −797bp, worth
  remembering as right-edge losers, but they are sample truncation, not
  survivorship.

Residual risk: a market delisted individually in Jan–May and absent from the
harvest entirely cannot be ruled out from disk. Given whole-dex deaths are
retained and the dominant deployer shows zero deaths, this is now a low-priority
verification, not a blocking one.

## Check 2 — Real spread costs: 20bp is conservative where measurable

For events on markets with raw L4 trade coverage, effective spread was
estimated from the within-minute gap between mean taker-BUY and taker-SELL
prices, at both the entry hour and exit hour (a marketable order pays ~half the
effective spread per side).

29 events measurable (xyz:ARM, RKLB, NBIS, MRVL; Jun–Jul):

| Cost component | Median | p95 |
|---|---:|---:|
| Round-trip spread | 4.2bp | 7.9bp |
| Total incl. 9bp fees | **13.2bp** | 16.9bp |

The report's 20bp hurdle overstates costs by ~7bp on these names; repricing the
covered events with measured costs moves their mean from +61.5 to +68.3bp.

**Caveat:** coverage is precisely the liquid corner of the universe. The exotic
young contracts that carry many events (xyz:WDC, ZHIPU, PURRDAT, SNDK, CBRS,
DRAM, km:SILVER…) have no trade data on disk; their spreads are unmeasured and
plausibly much wider. The report's own finding that raising the liquidity floor
to $5–10M *strengthens* the mean gives a fallback: the strategy can retreat to
names where 13bp is verified.

## Check 3 — Oracle-basis split: not basis convergence, and the rebound is venue premium

Hypothesis tested: the −8% screen is a noisy proxy for a large perp−oracle
residual (same object as the harvester's oracle conditioning). **Refuted.**
For all 23 covered events (5 liquid xyz single names, Jun 20–Jul 8):

- The oracle (real underlying) fell essentially the **full** −8%+ alongside the
  perp: median 3-day residual −0.2pp, worst −2.1pp. Entry basis was tiny
  (mostly within ±35bp). There is no dislocation at entry to converge.
- Decomposing the 24h hold: the underlying **kept falling** (−93.6bp mean)
  while the perp was flat gross (+10.7bp). The perp's excess over its oracle
  was **+104.3bp (t=1.44, n=23)** — whatever rebound exists in this subset is
  the perp premium expanding against the oracle, not the stock recovering.
- Two outliers dominate (xyz:NBIS 2026-07-07: +1,655bp excess); nothing here is
  significant on its own.

Two implications:

1. On liquid US single names in Jun–Jul the strategy was ~flat net. The
   discovery round's Jun–Jul profits came from the **exotic uncovered names** —
   exactly where costs are also unmeasured (Check 2 caveat). The measurable
   corner is weak; the profitable corner is unmeasurable from disk.
2. The candidate is not the familiar basis-convergence object. If the excess-
   vs-oracle pattern holds up, the mechanism is a venue-local premium cycle on
   beaten-down young contracts — closer kin to the harvester's perp-side
   overshoot than to underlying mean reversion, but at 24h scale and unhedged.

## Bottom line for the forward test

The frozen shadow-forward test remains the right next step, with two additions
to its logging spec:

- **Log oracle_px and mark_px at entry, exit, and hourly** for every signal, so
  each forward trade decomposes into underlying move vs venue premium. If the
  edge is venue premium, a hedged variant (short the underlying or a twin)
  becomes the natural second experiment.
- **Record quoted spread and top-of-book depth at signal time on the exotic
  names** — that is the missing cost number, and shadow observation is the only
  free way to get it.

Survivorship is no longer a first-order objection. Costs are not either, for
the liquid half. The open question the forward test must answer is whether the
exotic-name profits survive their real (unknown) spreads.
