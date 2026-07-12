# HIP-3 strategy discovery round

**Research date:** 2026-07-11  
**Scope:** New directional, event-driven, relative-value, flow, and microstructure strategies for a small Hyperliquid HIP-3 account  
**Status:** Exploratory research; no strategy in this report has been validated in a live account

## Executive summary

This round searched the available HIP-3 data without restricting the mandate to
market making. The work covered directional taker strategies, lifecycle effects,
wallet flow, oracle leadership, forced-flow continuation, cross-venue lead-lag,
ordinary price shocks, and passive-maker niches.

One new candidate survived assumed trading costs and broad robustness checks:
**post-listing three-day exhaustion reversal**. Contracts between 7 and 55 days
old that fall at least 8% over three days tend to rebound over the following
18–24 hours. The cleanest expression for a small account is long-only, selecting
at most the largest qualifying decline each day.

The long-only rule returned approximately **+136.9 bp per equal-weight trade-day
after a conservative 20 bp round-trip cost**, with a date-clustered t-statistic
of 2.41 across 217 events and 78 trade-days. The top-one daily implementation
returned +137.9 bp net with t=2.57 across 127 events. Chronological splits,
threshold variations, age bands, and leave-one-market-out checks remained
positive.

This is not yet proven alpha. The rule was discovered in sample, the history is
only about six months, first candle is used as a listing-date proxy, and the
current-universe harvest may omit delisted contracts. The appropriate next step
is a frozen shadow-forward test, not immediate scaling.

Most shorter-horizon signals failed because their gross predictability was less
than taker costs. This is an important program-level result: the more promising
HIP-3 opportunities appear to involve large, slow dislocations tied to venue
lifecycle or oracle anchoring, rather than generic minute-to-minute momentum or
reversal.

## Data available

The repository contained approximately 24 GB of local market data at the time of
the study:

| Dataset | Approximate size or rows | Coverage/use |
|---|---:|---|
| Full L2 books | 15 GB | Queue-aware passive-fill and depth research |
| Trades | 3.7 GB | Tick and minute-bar event studies |
| Quotes | 3.6 GB | Executable-price and spread research |
| Hyperliquid oracle feed | 737 MB | Oracle/perp divergence and leadership |
| HIP-3 hourly candles | 548,869 rows | 182 markets, primarily 2026-01-01 through 2026-07-10 |
| HIP-3 daily candles | 22,995 rows | Listing lifecycle and daily cross-section |
| Funding observations | 586,113 rows | Hourly funding, exact holding-period funding |
| Wallet-attributed signed taker flow | 262,115 wallet-days | 13 markets, 2026-05-27 through 2026-07-08 |
| Simulated L2 fills | 2,204,391 rows | Eight index-like HIP-3 markets, 2026-03-11 through 2026-06-08 |
| Trade-minute bars | 879,746 rows | 13 markets, 2026-03-11 through 2026-07-08 |

The most relevant source artifacts were:

- `data/reports/study3_candles_1d.parquet`
- `data/reports/study3_candles_1h.parquet`
- `data/reports/study3_funding_all.parquet`
- `data/reports/study3_fee_table.parquet`
- `data/reports/study1_fills_l2.parquet`
- `data/reports/ff_minute_bars.parquet`
- `data/reports/oracle_bars/`
- `data/reports/walletflow_taker_signed_daily.parquet`
- `data/reports/walletflow_maker_daily.parquet`

## Search design

The discovery work was divided into independent research lanes:

1. **Lifecycle and cross-sectional strategies:** contract age, recent returns,
   volume, funding, listing behavior, and daily/hourly holding periods.
2. **Microstructure and oracle strategies:** oracle leadership, standardized
   trade shocks, forced-flow continuation, depth imbalance, and cross-venue
   lead-lag.
3. **Wallet and regime strategies:** total signed flow, dominant-wallet flow,
   frozen whale selection, flow propagation, and maker concentration.
4. **Small-account execution screen:** chronological maker niches and U.S.
   single-name overnight-gap behavior.

Existing ledgers were treated as a do-not-rediscover list. Previously rejected
funding carry, funding impulse, generic off-hours making, and the already-known
oracle-flat harvester were not presented as new findings.

Unless stated otherwise, taker strategies were charged 4.5 bp per side, or 9 bp
round trip, matching the fee assumption in the local HIP-3 fee table. The lead
lifecycle study used a more conservative **20 bp round-trip hurdle**, consisting
of 9 bp in fees and 11 bp in additional spread/slippage. Exact hourly funding was
included in its return calculation.

## Lead candidate: post-listing three-day exhaustion reversal

### Economic hypothesis

Recently listed HIP-3 contracts attract speculative positioning before their
liquidity and participant base mature. A sufficiently large multi-day move can
exhaust the dominant directional flow. The resulting correction is slow rather
than immediate, developing over approximately 18–24 hours.

This differs from the previously observed unconditional week-one volatility
elevation. The strategy waits until after the first week and requires a large
directional move.

### Frozen candidate rule

At each 00:00 UTC daily boundary:

1. Define listing age as days since the contract's first observed daily candle.
2. Require age of at least 7 days and less than 56 days.
3. Exclude contracts first observed on 2026-01-01 because their true listing date
   is left-censored by the data harvest.
4. Require trailing seven-session median notional volume of at least $1 million.
   The signal day is excluded from this liquidity calculation.
5. Compute the close-to-close return over the preceding three sessions.
6. Go long if the return is less than or equal to -8%.
7. The symmetric research rule goes short if the return is greater than or equal
   to +8%, although the short leg is not strong enough to recommend on its own.
8. Enter at the next available hourly open after the daily signal is known.
9. Exit 24 hours later using a marketable order.
10. If constrained to one position, select the contract with the largest absolute
    three-day move.

For the initial small-account version, the preferred rule is **long-only after a
three-day fall of at least 8%, with at most one position at a time**.

### Main results

| Variant | Complete events | Trade-days | Markets | Net result | t-statistic | 95% bootstrap CI |
|---|---:|---:|---:|---:|---:|---:|
| Equal-weight long and short signals | 409 | 126 | 55 | +146.6 bp/day | 3.54 | +67.2 to +227.9 bp |
| Largest signal each day | 127 | 126 | 33 | +137.9 bp/trade | 2.57 | +35.8 to +244.8 bp |
| Long after a fall | 217 | 78 | — | +136.9 bp/day | 2.41 | +25.7 to +248.6 bp |
| Short after a rally | 197 | 97 | — | +95.3 bp/day | 1.66 | -14.8 to +208.2 bp |

All results above are after the 20 bp round-trip cost assumption and include
funding. Funding contributed only about +2.1 bp per event overall, so it does not
explain the effect.

The equal-weight daily distribution was wide:

- Winning trade-days: 58.7%
- Median: +39.7 bp
- 5th percentile: approximately -479 bp
- 95th percentile: approximately +1,112 bp
- Historical top-one unlevered maximum drawdown: approximately -18.2%

The mean is therefore economically attractive but accompanied by substantial
single-position risk. Leverage would be inappropriate during validation.

### Holding-period shape

The edge did not appear immediately:

| Holding period | Approximate net result |
|---:|---:|
| 1 hour | -20 bp |
| 2 hours | +12 bp |
| 6 hours | +18 bp |
| 12 hours | +49 bp |
| 18 hours | +113 bp |
| 24 hours | +144 bp |

The slow development argues against interpreting the result as a brief stale
quote or candle-boundary artifact. It also means the strategy carries meaningful
overnight directional risk.

### Robustness checks

Threshold sensitivity for contracts aged 7–55 days remained positive after the
20 bp hurdle:

| Absolute three-day threshold | Net result | t-statistic |
|---:|---:|---:|
| 8% | +143.9 bp | 3.51 |
| 10% | +108.5 bp | 2.26 |
| 14% | +165.6 bp | 2.34 |
| 15% | +184.4 bp | 2.27 |
| 20% | +363.2 bp | 2.87 |

Chronological stability was also positive:

| Split | Earlier sample | Later sample |
|---|---:|---:|
| Before May / May–July | +113.8 bp, t=1.96 | +176.5 bp, t=3.04 |
| Before June / June–July | +131.8 bp, t=2.57 | +172.2 bp, t=2.59 |

These are stability splits, not honest untouched out-of-sample tests: the final
parameters were selected during the same research session.

Other checks:

- Every calendar month in the sample was positive.
- Age bands 7–14, 14–21, 21–28, 28–42, and 42–56 days were all positive.
- The minimum leave-one-market-out result was approximately +137 bp.
- Raising the liquidity floor to $5 million or $10 million strengthened the mean.
- XYZ-deployed contracts were strongest at approximately +172 bp, t=3.95.
- Non-XYZ contracts remained positive at approximately +74 bp but were not
  statistically strong.
- Excluding observations with subsequent absolute moves greater than 10% left
  approximately +60 bp, t=1.97.
- The same reversal rule on mature contracts aged at least 56 days was negative.

### Limitations

1. **In-sample selection:** return threshold, age window, and holding period were
   selected after screening related rules.
2. **Short history:** the panel covers only about six months.
3. **Survivorship:** the harvested universe is based on currently discoverable
   contracts and may omit delisted failures.
4. **Listing-date proxy:** first observed candle is not guaranteed to be the true
   launch timestamp.
5. **Candle execution:** hourly opens establish a markout, not guaranteed filled
   size or realized slippage.
6. **Tail risk:** the wide outcome distribution and roughly 18% historical
   drawdown are material for a $100 account.
7. **Multiple testing:** confidence intervals do not correct for the full strategy
   search process.

## Secondary candidate: positive overnight-gap continuation

An independent screen examined U.S. single-name HIP-3 contracts around the U.S.
equity open. Contracts were ranked cross-sectionally by the return from the prior
16:00 ET close to the current 09:00 ET hourly open. The strongest three positive
gaps were bought and held through approximately 15:00 ET.

Results:

- 391 positions across 135 trade-days
- Median opening gap: approximately +293 bp
- Mean continuation: +38.0 bp gross per position
- Approximately +29 bp after nominal 9 bp taker fees, before additional slippage
- Equal-day mean: +35.9 bp gross, t=1.38
- Post-April mean: +34.8 bp gross
- Post-May mean: +33.3 bp gross
- 5th/95th percentile outcomes: approximately -705/+702 bp

The direction was chronologically stable, but statistical strength was weak and
the distribution was extremely wide. The behavior may be ordinary post-gap drift
in the underlying equities rather than a HIP-3-specific inefficiency. It should
be recorded during forward testing but is not ready for capital.

## Wallet and participant-flow findings

No standalone wallet-flow strategy survived executable checks.

### Daily aggregate signed flow

- 404 usable market-days across 13 HIP-3 markets
- Directional persistence: +5.7 bp gross with approximately 18.2 bp standard
  error
- Net after assumed 9 bp round-trip taker fees: -3.3 bp
- Extreme top-decile flow reversal: +21.3 bp gross, but statistically weak and
  threshold-fragile

### Frozen whale selection

Wallets were selected using 2026-05-27 through 2026-06-16 and tested from
2026-06-17 through 2026-07-08:

- Top-one whale following: 140 observations, +12.1 bp gross, approximately
  +3.1 bp after fees
- Top-three and broader baskets were flat or negative
- Results disagreed sharply by market

The frozen selection did not validate persistent wallet-following alpha.

### XYZ100 flow propagation

Daily XYZ100 imbalance appeared to predict the next UTC-session direction of
xyz:SP500:

- 41 days
- +30.2 bp gross
- Approximately 66% winning days
- Roughly +21 bp after nominal taker fees

However, the result was unstable by weekday and failed replication at hourly
frequency across 937 hours. It is more consistent with a calendar coincidence or
coarse aggregation artifact than established alpha.

### Flow exhaustion

A direction flip after at least two hours of same-sign flow produced +5.7 bp
gross over the next hour in XYZ100 and +3.0 bp in SP500. This is below taker
costs. It may eventually be useful as a passive-execution filter, but not as a
directional taker strategy.

## Microstructure and oracle findings

No new short-horizon directional strategy cleared costs.

### Oracle-lead continuation

Signal:

- Oracle moves at least 20 bp over five minutes.
- Perp has moved in the same direction but no more than half as far.
- Follow the oracle direction, with a 30-minute market cooldown.

Across 25 markets from 2026-06-17 through 2026-07-08:

- 6,278 events over 22 days
- Gross continuation of +7.1, +7.4, +7.9, and +8.0 bp at 1, 5, 15, and 30 minutes
- The second half of the sample weakened to +6.6 bp at 15 minutes and +6.4 bp at
  30 minutes

The gross edge is below the 9 bp round-trip taker fee before spread or slippage.
The minute-bar design also grants an unrealistically favorable same-minute entry.
Most of the move occurs within the first minute, so only a future tick-level,
low-latency implementation could plausibly revisit it.

### Standardized price shocks

Five-minute returns were standardized by trailing 24-hour median absolute
movement using 879,746 trade-minute bars across 13 markets.

- At absolute z-score at least 4: 9,410 events, with only +1.1/+2.0/+2.2 bp
  continuation at 15/30/60 minutes
- At absolute z-score at least 5: 6,685 events, with +1.1/+2.1/+2.7 bp
- Reversal was correspondingly negative or indistinguishable from zero

Neither direction approached transaction costs.

### Forced-flow following

Using the existing burst detector, entering after the event's completed minute,
and imposing a 30-minute cooldown produced 1,127 SKHX/SMSN events over 41 days.

- Directional continuation was negative at 5, 15, 30, and 60 minutes overall.
- Even bursts with rate multiple at least 10 produced only +3.3 bp at 30 minutes
  and +4.8 bp at 60 minutes.

The signal was below costs and unstable by market and direction.

### Cross-venue US500 lead-lag

The study tested `xyz:SP500`, `cash:USA500`, `km:US500`, and `flx:USA500` using
next-minute entries and both directional and hedged exits. Liquid-market pairs
were flat or negative. Apparent flx lag effects had only 7–18 events. A hedged
two-leg trade would pay approximately 18 bp in round-trip taker fees before
spread and slippage.

## Passive-maker screen

The 2.2 million simulated L2 fills were divided chronologically and screened by
market, side, size bucket, UTC hour, and trading-session label. No grouping with
at least ten days in both halves had positive net 10-minute markout in both the
early and late sample.

This reinforces the prior conclusion that generic top-of-book making is not a
standalone edge in the studied index-like markets. Passive execution should be
used to improve a separate signal, not assumed to be profitable by itself.

## Consolidated negative results

The following did not produce a deployment-ready strategy:

- Generic one-day reversal
- Generic mature-contract three-day reversal
- Volume-shock reversal
- Close-location-value reversal
- Unconditional listing-age directional drift
- Funding level, impulse, and standalone carry, as documented in earlier ledgers
- Daily aggregate wallet-flow persistence or reversal
- Frozen whale-wallet following
- Hourly cross-market wallet-flow propagation
- Generic minute shock continuation or reversal
- Completed forced-flow burst following
- Liquid US500 cross-venue lead-lag
- Chronologically stable passive-maker niches

## Interpretation

Three broad conclusions stand out:

1. **Fees dominate ordinary short-horizon prediction.** Several signals had the
   correct direction, but only 1–8 bp of gross movement. They are not strategies
   at current assumed taker costs.
2. **Young-contract exhaustion is different from mature-market behavior.** The
   three-day reversal is present during weeks 2–8 and absent after day 56, which
   is consistent with a venue-lifecycle mechanism.
3. **The strongest research objects operate at different timescales.** The
   existing oracle-flat harvester is a short-horizon microstructure effect; the
   new lifecycle reversal is an 18–24-hour directional effect. If both survive
   forward testing, they could become complementary portfolio components.

## Small-account recommendation

A $100 account cannot support broad cross-sectional diversification, and its
primary objective should be avoiding ruin while evidence accumulates. This study
does not justify immediate leveraged deployment.

The preferred path is:

1. Freeze the long-only exhaustion rule exactly as specified above.
2. Generate a daily signal file without changing parameters.
3. Shadow every signal and record contemporaneous bid, ask, depth, attainable
   size, funding, and the 1h/2h/6h/12h/18h/24h outcomes.
4. Reconstruct authoritative listing and delisting history to remove survivorship
   and listing-date uncertainty.
5. Replay the historical signals against raw trades or L2 to validate entry and
   exit slippage.
6. After an adequate forward sample, consider minimum-sized, unlevered positions.
7. Keep the weaker short leg disabled unless it independently earns a positive
   forward confidence interval.

## Frozen forward-test specification

To prevent research drift, the first forward test should use these exact values:

```text
Universe:       HIP-3 contracts with verified age 7–55 days
Liquidity:      trailing 7-session median notional volume >= $1,000,000
Signal:         close / close[t-3] - 1 <= -8.0%
Direction:      long only
Signal time:    00:00 UTC daily boundary
Entry:          first executable observation after signal time
Selection:      largest absolute qualifying decline if more than one signal
Maximum trades: one concurrent position
Planned exit:   24 hours after entry
Diagnostics:    1h, 2h, 6h, 12h, 18h, and 24h
Cost ledger:    actual fees, spread, slippage, and funding recorded separately
Parameter edits:none until the forward evaluation date
```

The forward record should report both signal markout and actually attainable P&L.
The strategy should not be promoted from candidate status solely because its
first few observations win.

## Follow-up research round

The initial report identified listing-clock accuracy, survivorship, factor
decomposition, executable prices, low-fee venues, and system events as the most
valuable unresolved questions. A second independent research round investigated
those questions using the existing local data.

### Revised lifecycle verdict

The lifecycle reversal survives improved inception clocks and a broader
defensible birth cohort. It also becomes stronger after removing the
contemporaneous HIP-3 cross-sectional return. The current evidence therefore
supports an `xyz`-specific, venue-relative exhaustion effect more strongly than
either a generic underlying reversal or a universal HIP-3 lifecycle effect.

Execution remains unresolved. None of the historical lifecycle signals overlaps
the available raw quote/L2 archive, and the small trade-print fallback is too
weak to establish executable size. The strategy remains a forward-test candidate.

### Listing-clock audit

The harvested universe contains:

- 225 HIP-3 metadata entries
- 179 markets with daily and hourly candle history
- 180 markets with funding history
- 45 registered markets with no observed trade history
- One funding-only market, `hyna:LIT`
- 38 histories left-censored at 2026-01-01
- 141 directly observable births

First hourly trading is the best defensible inception clock. Across the 141
observable births, first funding and first hourly candle are always within 12
hours. The daily-candle proxy precedes actual hourly trading by a median of 15
hours.

The metadata field `lastGrowthModeChangeTime` is not a universal listing time.
It agrees with first hourly trading within two days for only 59 of 118 comparable
markets; discrepancies range from -46 to +135 days. The field can represent a
later parameter change or a registration that precedes actual trading.

Long-only strategy results by inception clock, using the original 20 bp cost
hurdle:

| Inception clock | Events | Trade-days | Markets | Net result | t-statistic |
|---|---:|---:|---:|---:|---:|
| First daily candle | 214 | 78 | 50 | +134.7 bp/day | 2.36 |
| First hourly candle | 211 | 76 | 50 | +152.8 bp/day | 2.77 |
| First funding observation | 209 | 76 | 50 | +148.7 bp/day | 2.72 |
| Conservative hybrid clock | 226 | 83 | 53 | +115.5 bp/day | 2.13 |

The conservative hybrid uses growth-mode time only when corroborated within two
days of first hourly trading, plus credible pre-January timestamps to resolve
left-censored contracts. This is the broadest defensible local cohort.

### Survivorship audit

The current metadata marks 112 entries as delisted. These comprise 45
never-traded registrations, approximately 66 whole-dex stopped histories, and
one boundary case. The frozen long-only strategy contains 45 events on 15 markets
that subsequently stopped trading.

Those stopped-market events earned +158.5 bp event-weighted. Their date-clustered
mean is -7.4 bp because many whole-dex events occur together. Crucially, no
strategy entry occurs within 21 days of the market's final candle, and there is
no observed case of entering and then losing the exit because the contract
disappears. All four missing exits under the hourly clock are July 9 signals
whose targets fall beyond the data-harvest boundary.

The post-May vendor census is strong: 1,072,615 CoinAPI trade, quote, and oracle
objects from May 8 through July 8 enumerate 178 HIP-3 names. Every one remains
present in the July metadata and candle panel. No traded-then-removed post-May
market was found.

Pre-May individually removed markets cannot be recovered from the single local
metadata snapshot, so the result cannot be called fully survivorship-free. To
erase the observed event-weighted total of approximately 32,350 bp would require
roughly one of the following omitted populations:

- 65 events losing 500 bp each
- 33 events losing 1,000 bp each
- 13 events losing 2,500 bp each
- Seven events losing 5,000 bp each
- Four complete-loss events

That is implausible for the observed and post-May universe, but it cannot be
strictly ruled out for the unknown pre-May population.

The more important weakness is deployer breadth. `xyz` produces approximately
+179 bp/day with t=3.21, while non-`xyz` markets produce -37 bp/day with t=-0.43
when clustered by date. The strategy should therefore be described as an
`xyz` lifecycle effect until another deployer independently validates it.

### Common-factor and oracle decomposition

The raw long-only sample reproduces at 214 events, 78 trade-days, and 50 markets,
with +134.7 bp/day after the 20 bp cost assumption and t=2.36.

Removing the same-day HIP-3 cross-sectional median return strengthens the
subsequent venue/idiosyncratic component to approximately +165.6 bp/day gross,
t=3.49. A fixed residual signal,

```text
contract three-day return - HIP-3 cross-sectional median <= -8%
```

with the original age and liquidity filters unchanged, produces:

- 170 events across 76 trade-days
- +156.7 bp/day net, t=2.72
- Top-one daily selection: +195.5 bp/day, t=2.72

This is a useful confirmation, not a replacement production rule: the residual
variant was created after observing the raw effect and must be frozen before any
forward comparison.

Direct oracle decomposition is available for only 23 events across nine days and
five markets. In that subset:

- Perp gross return: +41.4 bp/day
- Underlying/oracle return: -90.2 bp/day
- Perp outperformance versus oracle: +131.6 bp/day, t=1.21

The subset suggests venue-premium expansion rather than ordinary underlying
reversal or simple entry-basis convergence. It is too small and outlier-heavy for
a firm mechanism claim.

### Execution audit

There is zero exact overlap between lifecycle signals and the raw quote/L2
archive. Signals in the markets with historical books occurred before archive
coverage, while the later exotic lifecycle names have trades but no books.

A first-aggressive-print fallback covers only 26 events, 14 days, and four liquid
`xyz` markets. Entry and exit use the first observed qualifying print within ten
minutes; results below include 9 bp in taker fees but do not prove book depth:

| Minimum print-size gate | Net result | t-statistic |
|---:|---:|---:|
| $10 | +93.3 bp/day | 0.62 |
| $25 | +65.2 bp/day | 0.31 |
| $50 | +112.1 bp/day | 0.43 |

Funding averages -4.4 bp over these events. The sample is directionally
compatible with the candle result but statistically uninformative.

Risk paths are substantial: median 24-hour maximum adverse excursion is -234 bp,
and its 5th percentile is approximately -1,008 bp. A live pilot must avoid
leverage and record full bid/ask and depth rather than only trade prints.

### Low-fee venue audit

The cached hyna fee configuration implies approximately 0.50 bp taker cost per
side. The base fee remains an account-independent project assumption, so the
study charged 4 bp round trip: approximately 1 bp in fees plus a 3 bp execution
reserve.

Hyna had 22 markets with hourly candles, but no market currently passed the
project's $1 million/day snapshot liquidity floor. Volume had deteriorated
substantially: current snapshot volume was approximately $0.96M for BTC, $0.62M
for ETH, $0.47M for HYPE, and $0.18M for SOL.

The low fee did not rescue standardized shocks, volume impulses, or BTC-relative
dislocations on the liquid subset. A weak one-hour shock reversal appeared under
a permissive $100k/day historical filter, then became negative when the
$1M/day filter was enforced. An extreme-funding reversal was positive but
insignificant and driven by illiquid `hyna:BASED`; BTC, ETH, and HYPE supplied
only three combined events.

No hyna strategy is ready for funding. Thin and deteriorating liquidity dominates
the nominal fee advantage.

### System-order event screen

The `T-HLSYSTEMEVENTS` archive covers only June 17 through July 8 and contains no
explicit deployment, delisting, OI-cap, leverage, oracle-change, or liquidation
event types. Its largest categories are transfers. It does contain 1,128 mapped
HIP-3 order actions, almost all IOC orders.

A causal exploratory rule faded the prior hour's signed HIP-3 system-order
notional at the next hourly open. Across 347 market-hour signals and 21 days, the
equal-day gross reversal was:

| Hold | Gross result | t-statistic |
|---:|---:|---:|
| 1 hour | +22.2 bp | 1.68 |
| 2 hours | +29.3 bp | 2.85 |
| 4 hours | +38.5 bp | 2.81 |

The result weakens in the second half to +3.6/+14.6/+26.6 bp at 1/2/4 hours and
is concentrated in `xyz:SPCX`, which supplies 160 of 347 signals. Excluding SPCX
leaves only about -1.2 bp and +2.6 bp after a conservative 20 bp hurdle at two
and four hours. The semantic source of these orders is also not established.

This is a narrow forward-monitoring lead for SPCX, not a general strategy.

### Updated priority

The next work should now be narrower:

1. Forward-log the frozen raw and residual `xyz` lifecycle signals with bid, ask,
   multiple depth levels, oracle, funding, and actual attainable size.
2. Acquire or reconstruct pre-May metadata snapshots only if they can identify
   traded markets absent from the current panel.
3. Keep raw and residual lifecycle variants side by side without changing their
   thresholds during the forward period.
4. Monitor SPCX system-order reversal, but do not allocate capital until the
   event semantics and out-of-sample persistence are established.
5. Do not spend further research time on generic low-fee hyna signals without a
   material recovery in liquidity.
