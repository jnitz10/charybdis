"""Causal, cost-aware Study-3 cross-sectional carry backtests."""

from __future__ import annotations

from bisect import bisect_right
from datetime import datetime, timedelta
import math
from typing import Mapping, Sequence

import polars as pl


def assign_deciles(signals: pl.DataFrame) -> pl.DataFrame:
    """Label the lowest/highest tenth, using ceil(n/10) per tail."""

    clean = signals.select("market", "signal").drop_nulls().sort(["signal", "market"])
    count = max(1, math.ceil(clean.height / 10)) if clean.height else 0
    bottom = clean.head(count).with_columns(pl.lit("bottom").alias("decile"))
    top = clean.tail(count).with_columns(pl.lit("top").alias("decile"))
    return pl.concat([bottom, top]).sort(["decile", "signal", "market"])


def turnover_cost(
    market: str,
    *,
    turnover: float,
    half_spread_bps: float,
    fee_table: pl.DataFrame,
) -> float:
    """One-way taker fee plus half-spread, charged to absolute turnover."""

    dex = market.split(":", 1)[0]
    row = fee_table.filter(pl.col("dex") == dex)
    if row.height != 1:
        raise ValueError(f"fee table must contain exactly one row for {dex!r}")
    fee_bps = float(row["effective_taker_bps"][0])
    return abs(float(turnover)) * (fee_bps + float(half_spread_bps)) / 10_000.0


def trailing_hedge_beta(
    candles: pl.DataFrame,
    rebalance_time: datetime,
    target: str,
    hedge_markets: list[str],
    *,
    lookback: timedelta = timedelta(days=30),
    min_observations: int = 24,
) -> float | None:
    """OLS beta of target log returns on an equal-weight hedge basket."""

    markets = [target, *hedge_markets]
    history = candles.filter(
        pl.col("market").is_in(markets)
        & (pl.col("time_open") >= rebalance_time - lookback)
        & (pl.col("time_open") < rebalance_time)
    )
    wide = history.pivot(on="market", index="time_open", values="close").sort("time_open")
    if any(market not in wide.columns for market in markets):
        return None
    returns = wide.select(
        "time_open",
        *[(pl.col(market).log().diff()).alias(market) for market in markets],
    ).drop_nulls()
    if returns.height < min_observations:
        return None
    target_values = [float(v) for v in returns[target].to_list()]
    hedge_values = [
        sum(float(returns[m][i]) for m in hedge_markets) / len(hedge_markets)
        for i in range(returns.height)
    ]
    x_mean = sum(hedge_values) / len(hedge_values)
    y_mean = sum(target_values) / len(target_values)
    variance = sum((x - x_mean) ** 2 for x in hedge_values)
    if variance == 0.0:
        return None
    covariance = sum((x - x_mean) * (y - y_mean) for x, y in zip(hedge_values, target_values))
    return covariance / variance


def tradable_markets_for_period(
    candles: pl.DataFrame,
    candidates: list[str],
    rebalance_time: datetime,
    end_time: datetime,
) -> list[str]:
    """Markets with two real, post-rebalance closes; never forward-filled."""

    counts = (
        candles.filter(
            pl.col("market").is_in(candidates)
            & (pl.col("time_open") > rebalance_time)
            & (pl.col("time_open") < end_time)
            & pl.col("close").is_not_null()
        )
        .group_by("market")
        .len()
        .filter(pl.col("len") >= 2)
    )
    return sorted(counts["market"].to_list())


def strictly_after_candle_return(
    candles: pl.DataFrame,
    rebalance_time: datetime,
    end_time: datetime,
) -> float | None:
    """Close-to-close return excluding the candle at/containing rebalance."""

    close_col = "time_close" if "time_close" in candles.columns else "time_open"
    end_filter = pl.col(close_col) <= end_time if close_col == "time_close" else pl.col(close_col) < end_time
    eligible = candles.filter(
        (pl.col("time_open") > rebalance_time) & end_filter
    ).sort(close_col)
    if eligible.height < 2:
        return None
    first = float(eligible["close"][0])
    last = float(eligible["close"][-1])
    return last / first - 1.0


def funding_window(
    rows: Sequence[tuple[datetime, float]],
    start_exclusive: datetime,
    end_inclusive: datetime,
) -> list[float]:
    """Raw settlement values in ``(start, end]`` without time rounding."""

    times = [row[0] for row in rows]
    lo = bisect_right(times, start_exclusive)
    hi = bisect_right(times, end_inclusive)
    return [float(row[1]) for row in rows[lo:hi]]


def signal_cross_section(
    funding_by_market: Mapping[str, Sequence[tuple[datetime, float]]],
    markets: Sequence[str],
    rebalance_time: datetime,
    *,
    min_observations: int = 168,
) -> pl.DataFrame:
    """Trailing-seven-day means known at rebalance, requiring full hourly history."""

    records = []
    start = rebalance_time - timedelta(days=7)
    for market in markets:
        values = funding_window(funding_by_market.get(market, []), start, rebalance_time)
        if len(values) >= min_observations:
            records.append({"market": market, "signal": sum(values) / len(values)})
    return pl.DataFrame(records, schema={"market": pl.String, "signal": pl.Float64})


def position_targets(signals: pl.DataFrame, *, long_short: bool) -> dict[str, float]:
    """Gross-one decile targets: short-only 1.0; long-short 0.5 per side."""

    labels = assign_deciles(signals)
    top = labels.filter(pl.col("decile") == "top")["market"].to_list()
    bottom = labels.filter(pl.col("decile") == "bottom")["market"].to_list()
    result = {market: -1.0 / len(top) for market in top}
    if long_short:
        result = {market: weight * 0.5 for market, weight in result.items()}
        result.update({market: 0.5 / len(bottom) for market in bottom})
    return result


def decile_period_pnl(
    funding: pl.DataFrame,
    rebalance_time: datetime,
    end_time: datetime,
    *,
    side: str,
    lookback: timedelta = timedelta(days=7),
) -> float:
    """Funding-only PnL for one causal decile holding period.

    Signal settlements are in ``[t-lookback, t]``. PnL settlements are in
    ``(t, end]``; settlement rows are never backfilled into the hour they
    describe.
    """

    if side not in {"short", "long"}:
        raise ValueError("side must be 'short' or 'long'")
    signal = (
        funding.filter(
            (pl.col("time_exchange") >= rebalance_time - lookback)
            & (pl.col("time_exchange") <= rebalance_time)
        )
        .group_by("market")
        .agg(pl.col("funding_rate").mean().alias("signal"))
        .sort("signal", descending=side == "short")
    )
    if signal.is_empty():
        return 0.0
    count = max(1, math.ceil(signal.height / 10))
    selected = signal.head(count)["market"].to_list()
    paid = funding.filter(
        pl.col("market").is_in(selected)
        & (pl.col("time_exchange") > rebalance_time)
        & (pl.col("time_exchange") <= end_time)
    )
    sign = 1.0 if side == "short" else -1.0
    by_market = paid.group_by("market").agg(pl.col("funding_rate").sum())
    return sign * float(by_market["funding_rate"].sum()) / len(selected)
