"""Study-3 S-E cross-dex funding-spread estimators.

Funding rows are hourly settlement events and are never shifted backward. Rates
and APR values are decimals. Trading costs are bps and are read from the T0 fee
table supplied by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from statistics import median
from typing import Iterable, Mapping

import polars as pl

from charybdis.study3_census import estimate_ar1_half_life


APR_HOURS = 24.0 * 365.0

# Exact aliases confirmed against study3_universe.parquet. Every other coin is
# aligned only by exact coin identity; no fuzzy ticker matching is permitted.
UNDERLIER_ALIASES: dict[str, str] = {
    "SP500": "SP500",
    "US500": "SP500",
    "USA500": "SP500",
    "USTECH": "USA100",
    "USA100": "USA100",
    "XYZ100": "USA100",
}


@dataclass(frozen=True)
class TwinPair:
    underlier: str
    market_a: str
    market_b: str

    @property
    def pair_id(self) -> str:
        return f"{self.market_a}|{self.market_b}"


@dataclass(frozen=True)
class RoundTripCost:
    maker_bps: float
    taker_bps: float


def market_underlier(market: str) -> str:
    """Map a market to an exact audited underlier label."""

    parts = market.split(":", 1)
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"HIP-3 market must be dex:coin, got {market!r}")
    return UNDERLIER_ALIASES.get(parts[1], parts[1])


def align_twin_pairs(markets: Iterable[str]) -> list[TwinPair]:
    """Return all cross-dex pairs within each exact underlier group."""

    groups: dict[str, list[str]] = {}
    for market in sorted(set(markets)):
        underlier = market_underlier(market)
        groups.setdefault(underlier, []).append(market)
    pairs: list[TwinPair] = []
    for underlier, members in sorted(groups.items()):
        for left_index, left in enumerate(members):
            left_dex = left.split(":", 1)[0]
            for right in members[left_index + 1 :]:
                if right.split(":", 1)[0] != left_dex:
                    pairs.append(TwinPair(underlier, left, right))
    return pairs


def round_trip_cost_bps(
    market_a: str,
    market_b: str,
    *,
    fee_table: pl.DataFrame,
    half_spread_bps: Mapping[str, float],
) -> RoundTripCost:
    """Cost entry and exit on both legs under explicit execution conventions.

    Maker orders rest and pay maker fees without crossing the spread. Taker
    orders cross each leg's half-spread at both entry and exit.
    """

    required = {"dex", "effective_maker_bps", "effective_taker_bps"}
    missing = required - set(fee_table.columns)
    if missing:
        raise ValueError(f"fee table missing columns: {sorted(missing)}")

    def fee(market: str, column: str) -> float:
        dex = market.split(":", 1)[0]
        rows = fee_table.filter(pl.col("dex") == dex)
        if rows.height != 1:
            raise ValueError(f"fee table must contain exactly one row for {dex!r}")
        value = float(rows[column][0])
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"invalid {column} for {dex!r}")
        return value

    spreads = []
    for market in (market_a, market_b):
        if market not in half_spread_bps:
            raise ValueError(f"missing half-spread for {market!r}")
        value = float(half_spread_bps[market])
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"invalid half-spread for {market!r}")
        spreads.append(value)
    spread_sum = sum(spreads)
    maker = fee(market_a, "effective_maker_bps") + fee(market_b, "effective_maker_bps")
    taker = fee(market_a, "effective_taker_bps") + fee(market_b, "effective_taker_bps")
    return RoundTripCost(2.0 * maker, 2.0 * (taker + spread_sum))


def amortized_breakeven_apr(cost_bps: float, persistence_hours: float) -> float:
    """Convert a round-trip bps cost to APR over its amortization horizon."""

    cost = float(cost_bps)
    horizon = float(persistence_hours)
    if not math.isfinite(cost) or cost < 0:
        raise ValueError("cost_bps must be finite and non-negative")
    if not math.isfinite(horizon) or horizon <= 0:
        raise ValueError("persistence_hours must be finite and positive")
    return (cost / 10_000.0) * APR_HOURS / horizon


def persistence_half_life_hours(
    absolute_differential: Iterable[float | None],
    times: Iterable[datetime] | None = None,
) -> float | None:
    """AR(1)-with-intercept half-life of an absolute hourly differential."""

    estimate = estimate_ar1_half_life(absolute_differential, times)
    return estimate.half_life_hours


def persistence_half_life_lag_pairs(frame: pl.DataFrame) -> float:
    """AR(1) half-life from precomputed genuine adjacent-hour lag pairs.

    The caller may cluster-bootstrap these rows safely: resampling rows or
    blocks cannot manufacture new temporal adjacency because ``lag_value`` and
    ``value`` were fixed before resampling.
    """

    required = {"lag_value", "value"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"lag-pair frame missing columns: {sorted(missing)}")
    pairs = [
        (float(left), float(right))
        for left, right in frame.select("lag_value", "value").iter_rows()
        if left is not None and right is not None
        and math.isfinite(float(left)) and math.isfinite(float(right))
    ]
    if len(pairs) < 2:
        return math.nan
    x_mean = sum(left for left, _ in pairs) / len(pairs)
    y_mean = sum(right for _, right in pairs) / len(pairs)
    denominator = sum((left - x_mean) ** 2 for left, _ in pairs)
    if denominator == 0.0:
        return math.nan
    phi = sum((left - x_mean) * (right - y_mean) for left, right in pairs) / denominator
    return math.log(0.5) / math.log(phi) if 0.0 < phi < 1.0 else math.nan


def breakeven_episode_durations(
    frame: pl.DataFrame, threshold_apr: float
) -> list[float]:
    """Lengths in hours of contiguous hourly observations above a threshold."""

    rows = frame.select("time", "abs_diff_apr").sort("time").iter_rows()
    durations: list[float] = []
    length = 0
    previous: datetime | None = None
    for timestamp, value in rows:
        exceeds = float(value) > threshold_apr
        contiguous = previous is not None and timestamp - previous == timedelta(hours=1)
        if exceeds:
            if not contiguous and length:
                durations.append(float(length))
                length = 0
            length += 1
        elif length:
            durations.append(float(length))
            length = 0
        previous = timestamp
    if length:
        durations.append(float(length))
    return durations


def median_episode_duration(frame: pl.DataFrame, threshold_apr: float) -> float:
    durations = breakeven_episode_durations(frame, threshold_apr)
    return float(median(durations)) if durations else math.nan


def utc_six_hour_block(timestamp: datetime) -> datetime:
    return timestamp.replace(
        hour=(timestamp.hour // 6) * 6, minute=0, second=0, microsecond=0
    )
