# Strategy Priors — Gut Ranking Before Any Data (2026-07-05)

Pre-registered instinct, written before Phase-A capture exists. Purpose: when
the census/markout data lands, check it against these priors honestly — the
data adjudicates, not the story. (Author's calibration note: the same gut
liked KXBTC15M's maker candidate, which lost money on counted night 1.)

## Ranked priors

### 1. Off-hours / weekend MM on equity & index perps (xyz, km/mkts) — TOP PICK

The one with a structural story for *why the flow is dumb*, which is what
actually pays makers. Evenings and Fri-close→Mon-open, HIP-3 is roughly the
only venue on earth where retail can trade "NVDA" or "SP500": captive,
impatient, uninformed flow — classic bucket-shop clientele. Meanwhile the
maker can compute a defensible fair almost the whole time: ES/NQ trade 23/6,
so xyz:SP500 / km:US500 off-hours means quoting against a live, public,
hedge-quality reference while counterparties have nothing.

- Edge is specifically the hours the underlying sleeps. During RTH everyone
  sees the real NBBO and repricing becomes a latency race — no edge there.
- Bleeders-vs-gappers discipline: indices/sector baskets first (smooth gap
  profile); single names only with an earnings/event calendar veto. One
  weekend gap through inventory on a single name = a month of spread.
- Open questions that could kill it: oracle/margin mechanics while the
  underlying is closed (frozen oracle + moving mark → liquidation behavior?);
  whether the deployer itself quotes that window with the same ES feed.

### 2. hyna crypto majors, hedged 1:1 on the main dex

Cleanest, most measurable, most boring: quote hyna:BTC, hedge instantly in
the deepest perp book in crypto, same chain, same margin rails, cheapest fee
scale of any dex (deployerFeeScale 0.1111). If the flow is real this is
near-pure spread capture with inventory risk measured in seconds.

- Existential question: does hyna have real flow, or incentive-farming wash?
  One census day + our own trade capture vs reported dayNtlVlm answers it.
- Expected outcome: real edge, tiny capacity. Worth having because the
  measurement→live path has almost no model risk.

### 3. Cross-dex oracle-lag taking — measure, don't build first

Four independent NVDA oracles, six GOLDs: someone's book is stale after every
sharp move, and early-venue stale books are real money. But: knife fight vs
other snipers, taker-fee-taxed, capacity-thin, and it's the toxic side of the
table — the side currently eating us on Kalshi. The oracle-forensics study
produces the lead/lag numbers for free; build only if they're screaming.

### Avoid initially: vntl pre-IPO (ANTHROPIC/OPENAI/SPACEX)

Seductive spreads, no public truth. Whoever trades against you may hold
secondary-market marks or allocation gossip — an information edge you cannot
detect, price, or hedge — plus uncontrolled deployer oracle re-marks on top.
Unmeasurable adverse selection is exactly what we've learned to walk away
from.

## Implications for the Phase-A shortlist

- Weight toward: index perps + 2–3 mega-caps on xyz **plus their km/cash
  twins** (cross-dex forensics), hyna BTC/ETH **plus main-dex twins**.
- Capture must span **at least two full weekends** — the off-hours hypothesis
  is untestable without them.
- Falsification: if off-hours simulated touch markout is not visibly better
  than RTH markout, prior #1 is dead regardless of how good the story sounds.
