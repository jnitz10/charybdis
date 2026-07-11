/** Popover content for every chart, plus the shared domain glossary.
 *  Sourced from the study reports in docs/reports/. */
import type { ReactNode } from 'react'

function H({ children }: { children: ReactNode }) {
  return <div className="pt-1 font-medium text-zinc-300">{children}</div>
}

function Dt({ term, children }: { term: string; children: ReactNode }) {
  return (
    <p>
      <span className="font-medium text-zinc-300">{term}</span> — {children}
    </p>
  )
}

export const SYMBOL_GLOSSARY = (
  <>
    <Dt term="dex:CODE">
      market keys are a HIP-3 builder-dex prefix (xyz:, km:, flx:, hyna:, vntl:, cash:, para:)
      plus the immutable on-chain asset code.
    </Dt>
    <Dt term="label ≠ code">
      the Hyperliquid app shows deployer-set display names (e.g. “xyz:SKHYNIX”); the API, the
      CoinAPI files, and every table here use the asset code (xyz:SKHX). Same asset, two names.
    </Dt>
    <Dt term="SMSN / SKHX">
      Samsung Electronics and SK Hynix perps. Their underlyings trade on KRX (Korea Exchange), so
      the studies condition on KRX open vs frozen — the oracle stops moving when KRX is closed.
    </Dt>
    <Dt term="SKHX vs SKHY">
      two distinct live assets (oracle px ≈ 1474.7 vs 169.39, OI caps $1B vs $250M) — a
      re-listing at a different unit scale, the same wart as km:US500 vs xyz:SP500.
    </Dt>
    <Dt term="L2 / L4 eras">
      the two CoinAPI coverage eras: HYPERLIQUID (quotes/book, from 2026-03-11) and HYPERLIQUIDL4
      (order-by-order with wallet attribution, from 2026-06-17). Where both cover a day, L4 wins.
    </Dt>
  </>
)

const PROXY_NOTE = (
  <Dt term="proxy events">
    heuristic forced-flow tags built from aggressive prints — HLSYSTEMEVENTS contains 0 confirmed
    liquidations over the whole window, so every “liquidation” here is a proxy, not ground truth.
  </Dt>
)

export const EXPLAIN: Record<string, ReactNode> = {
  study1_markout: (
    <>
      <p>
        Mean net maker markout (bps) for simulated passive fills in the selected market, by
        holding horizon, split by session: RTH, off-hours weekdays, weekends.
      </p>
      <H>How to read it</H>
      <p>
        Markout marks the fill against the book microprice a horizon later, net of maker fee and
        funding drift. More negative = worse for the maker. Stale quotes are excluded, and the L2
        fill simulation is an optimistic upper bound (no cancel or queue-priority visibility).
      </p>
      <H>What it feeds</H>
      <p>
        Study 1’s verdict: off-hours making is <em>not</em> better than RTH — session CIs overlap
        in 8/8 markets.
      </p>
    </>
  ),
  study2_dotwhisker: (
    <>
      <p>
        Mean net maker markout (bps) at the selected horizon for fills inside forced-flow proxy
        windows (blue) vs matched baseline windows (green), per market and pooled (ALL).
      </p>
      <H>How to read it</H>
      <p>
        Dot = point estimate; whisker = 95% cluster-bootstrap CI (clustered by window).
        Overlapping intervals = the conditions do not separate.
      </p>
      {PROXY_NOTE}
      <p>
        Post 2026-06-18 quote poisoning drops 39.5% of windows, so the comparison is confounded
        and conservative. Verdict: no exploitable maker edge around forced flow.
      </p>
    </>
  ),
  study3_census_scatter: (
    <>
      <p>
        One dot per HIP-3 market (183): x = funding-shock half-life in hours (how long a funding
        dislocation persists), y = mean funding APR (how big it is).
      </p>
      <H>How to read it</H>
      <p>
        Harvestable carry needs size <em>and</em> persistence. Median half-life is 1.3h, max
        9.9h — nothing survives to the 24h bar a carry position needs, however large the APR.
      </p>
      <H>What it feeds</H>
      <p>Study 3’s census verdict: 0/183 markets are carry-relevant.</p>
    </>
  ),
  study3_census_top: (
    <>
      <p>The 15 largest mean funding APRs across the census, with 95% CIs.</p>
      <H>How to read it</H>
      <p>
        Big APR alone is not edge: these dislocations decay within hours (see the half-life axis
        on the scatter) and typically reverse before a carry position can collect them.
      </p>
    </>
  ),
  study3_clock: (
    <>
      <p>
        Mean return (bps) inside ±minute brackets around the hourly funding settlement (blue) vs
        matched same-market baseline windows (green) — six bracket widths × two coverage groups.
      </p>
      <H>How to read it</H>
      <p>
        Dot = mean, whisker = 95% CI. A real funding-clock effect (prices drifting into or
        snapping back after settlement) would separate blue from green somewhere. 12/12 pairs
        overlap.
      </p>
      <p>
        Coverage: SKHX/SMSN use the full L4 window; the other eight markets are a 3.5-day
        recent-regime null only.
      </p>
    </>
  ),
  study3_spreads: (
    <>
      <p>
        Same-underlying perps listed on different HIP-3 dexes, ranked by mean |Δ funding APR| —
        the raw material for a cross-dex funding spread trade.
      </p>
      <H>How to read it</H>
      <p>
        A viable spread needs the funding differential to out-persist round-trip costs and basis
        noise. “basis p95 vs edge” compares the p95 excursion of the scale-invariant log-ratio
        basis against the funding edge collectable over the differential’s half-life.
      </p>
      <H>What it feeds</H>
      <p>0/57 pairs viable — basis swamps the edge everywhere.</p>
    </>
  ),
  study3_hazard: (
    <>
      <p>
        Forced-flow proxy event rate per market-hour, bucketed by the funding APR prevailing when
        the event window opened, with 95% CIs.
      </p>
      <H>How to read it</H>
      <p>
        If extreme funding <em>timed</em> forced flow, the high-APR buckets would sit above the
        low ones. Pooled rates drift up, but per-market rate-ratio CIs include 1 — the pooled
        slope is market composition, not timing.
      </p>
      {PROXY_NOTE}
    </>
  ),
  backtests_equity: (
    <>
      <p>
        Cumulative net return of the selected carry strategy across rebalances (sum of per-period
        net PnL over all markets held).
      </p>
      <H>How to read it</H>
      <p>
        The attribution tiles decompose the total into funding collected, price drift of the
        positions, and costs. The report CI on total return comes from the study’s bootstrap.
      </p>
      <H>What it feeds</H>
      <p>
        Study 3C: every variant loses — funding actually collected is swamped by price drift
        against the position. Carry is priced, not free.
      </p>
    </>
  ),
  backtests_drawdown: (
    <p>
      Peak-to-trough decline of the equity curve at each point — how deep underwater the strategy
      is relative to its best point so far.
    </p>
  ),
  backtests_sharpe: (
    <p>
      Sharpe over a rolling 30-rebalance window, annualized using the median spacing between
      rebalances. Needs 30 periods before it draws anything.
    </p>
  ),
  backtests_monthly: (
    <p>
      Net strategy return by calendar month (%). Green = positive, red = negative; the scale is
      symmetric around zero.
    </p>
  ),
  chartlab: (
    <>
      <H>Sources</H>
      <p>
        study3_1h/1d are the REST-harvested candles behind Study 3. raw_trades_1m/5m/1h are built
        on demand from the local CoinAPI tick archive (data/T-TRADES) — both coverage eras,
        L4 preferred where they overlap, corrupt files skipped with a warning.
      </p>
      <H>Indicators</H>
      <p>
        Pick from the dropdown or type <code className="text-zinc-300">name:params</code> —
        e.g. ema:50, bbands:20:2, macd:12:26:9. Params must be &gt; 0. New indicators are one
        decorated function in charybdis/console/indicators.py.
      </p>
      <H>Markets &amp; symbols</H>
      {SYMBOL_GLOSSARY}
    </>
  ),
}
