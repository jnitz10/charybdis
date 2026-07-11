"""Study 3 S-A funding census and persistence estimators.

Funding timestamps are settlement-event timestamps and are used without shifts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from statistics import median
from typing import Iterable, Sequence

import polars as pl

from charybdis.markout import cluster_bootstrap_ci


APR_FACTOR = 24.0 * 365.0
LIQUIDITY_FLOOR_USD = 1_000_000.0
MIN_RANK_WEEKS = 4
MAX_CONSECUTIVE_GAP_SECONDS = 5_400.0
REGIME_THRESHOLDS: tuple[tuple[str, float], ...] = (
    ("25", 0.25),
    ("100", 1.00),
    ("300", 3.00),
)
VALID_COVERAGE_STATUSES = {
    "complete",
    "candle_truncated",
    "funding_truncated",
    "no_data",
}


@dataclass(frozen=True)
class AR1Estimate:
    """OLS AR(1) slope with intercept and its stationary shock half-life."""

    phi: float | None
    half_life_hours: float | None
    pair_count: int


def estimate_ar1_half_life(
    values: Iterable[float | None], times: Iterable[datetime] | None = None
) -> AR1Estimate:
    """Fit ``y[t] = alpha + phi*y[t-1]`` by OLS on adjacent finite values.

    Half-life is defined only for ``0 < phi < 1``. Non-stationary, negative,
    constant, or insufficient series retain a null half-life rather than being
    coerced into a persistence value.
    """

    raw_values = list(values)
    raw_times = list(times) if times is not None else None
    pairs = _lagged_pairs(raw_values, 1, raw_times)
    if len(pairs) < 2:
        return AR1Estimate(None, None, len(pairs))
    x_mean = sum(left for left, _ in pairs) / len(pairs)
    y_mean = sum(right for _, right in pairs) / len(pairs)
    denominator = sum((left - x_mean) ** 2 for left, _ in pairs)
    if denominator == 0.0:
        return AR1Estimate(None, None, len(pairs))
    phi = sum(
        (left - x_mean) * (right - y_mean) for left, right in pairs
    ) / denominator
    half_life = math.log(0.5) / math.log(phi) if 0.0 < phi < 1.0 else None
    return AR1Estimate(phi, half_life, len(pairs))


def spearman_rank_correlation(
    left: Sequence[float], right: Sequence[float]
) -> float | None:
    """Return Spearman's rho using average ranks for ties."""

    pairs = [
        (float(x), float(y))
        for x, y in zip(left, right, strict=True)
        if math.isfinite(float(x)) and math.isfinite(float(y))
    ]
    if len(pairs) < 2:
        return None
    x_rank = _average_ranks([x for x, _ in pairs])
    y_rank = _average_ranks([y for _, y in pairs])
    return _pearson(x_rank, y_rank)


def compute_market_stats(funding: pl.DataFrame) -> pl.DataFrame:
    """Compute per-market hourly funding statistics from settlement rows."""

    required = {"market", "time_exchange", "funding_rate"}
    missing = required - set(funding.columns)
    if missing:
        raise ValueError(f"funding missing columns: {sorted(missing)}")
    rows: list[dict[str, object]] = []
    for market in funding["market"].unique(maintain_order=True).to_list():
        group = funding.filter(pl.col("market") == market).sort("time_exchange")
        rates = [float(value) for value in group["funding_rate"].to_list()]
        times = group["time_exchange"].to_list()
        apr = [value * APR_FACTOR for value in rates]
        ar1 = estimate_ar1_half_life(rates, times)
        ac1_pairs = _lagged_pairs(rates, 1, times)
        ac24_pairs = _lagged_pairs(rates, 24, times)
        row: dict[str, object] = {
            "market": market,
            "n_funding_hours": len(rates),
            "first_funding_time": min(times),
            "last_funding_time": max(times),
            "mean_apr": sum(apr) / len(apr),
            "median_apr": median(apr),
            "pct_positive_hours": sum(value > 0 for value in rates) / len(rates),
            "ac1": _lag_autocorrelation(rates, 1, times),
            "ac24": _lag_autocorrelation(rates, 24, times),
            "ac1_pair_count": len(ac1_pairs),
            "ac24_pair_count": len(ac24_pairs),
            "ar1_phi": ar1.phi,
            "shock_half_life_hours": ar1.half_life_hours,
            "ar1_pair_count": ar1.pair_count,
        }
        for label, threshold in REGIME_THRESHOLDS:
            lengths = _regime_lengths(apr, times, threshold)
            row[f"regime_{label}_count"] = len(lengths)
            row[f"regime_{label}_mean_hours"] = (
                sum(lengths) / len(lengths) if lengths else None
            )
            row[f"regime_{label}_median_hours"] = median(lengths) if lengths else None
        rows.append(row)
    return pl.DataFrame(rows)


def compute_weekly_rank_persistence(funding: pl.DataFrame) -> pl.DataFrame:
    """Measure lag-1 persistence of each market's weekly cross-sectional rank.

    Weeks are Monday-start UTC calendar weeks. Each weekly cross-section ranks
    markets by that week's mean hourly funding, using average ranks for ties.
    The market-level statistic is Spearman's rho between its rank series at
    weeks ``t-1`` and ``t``. Aggregate adjacent-week cross-sectional rho is
    repeated in the output as context and traceability.
    """

    required = {"market", "time_exchange", "funding_rate"}
    missing = required - set(funding.columns)
    if missing:
        raise ValueError(f"funding missing columns: {sorted(missing)}")
    weekly_values: dict[tuple[datetime, str], list[float]] = {}
    for market, timestamp, rate in funding.select(
        "market", "time_exchange", "funding_rate"
    ).iter_rows():
        week_start = datetime.combine(
            (timestamp - timedelta(days=timestamp.weekday())).date(),
            datetime.min.time(),
        )
        weekly_values.setdefault((week_start, market), []).append(float(rate))
    weeks: dict[datetime, dict[str, float]] = {}
    for (week, market), values in weekly_values.items():
        weeks.setdefault(week, {})[market] = sum(values) / len(values)

    ranked: dict[datetime, dict[str, float]] = {}
    for week, market_values in weeks.items():
        markets = sorted(market_values)
        ranks = _average_ranks([market_values[market] for market in markets])
        ranked[week] = dict(zip(markets, ranks, strict=True))

    ordered_weeks = sorted(ranked)
    pair_correlations: list[float] = []
    for prior, current in zip(ordered_weeks, ordered_weeks[1:], strict=False):
        shared = sorted(set(ranked[prior]) & set(ranked[current]))
        correlation = spearman_rank_correlation(
            [ranked[prior][market] for market in shared],
            [ranked[current][market] for market in shared],
        )
        if correlation is not None:
            pair_correlations.append(correlation)
    aggregate_mean = (
        sum(pair_correlations) / len(pair_correlations) if pair_correlations else None
    )
    aggregate_median = median(pair_correlations) if pair_correlations else None

    rows: list[dict[str, object]] = []
    all_markets = sorted({market for values in ranked.values() for market in values})
    for market in all_markets:
        series = [
            ranked[week][market] for week in ordered_weeks if market in ranked[week]
        ]
        rows.append(
            {
                "market": market,
                "weekly_rank_observations": len(series),
                "week_over_week_rank_corr": (
                    spearman_rank_correlation(series[:-1], series[1:])
                    if len(series) >= MIN_RANK_WEEKS
                    else None
                ),
                "cross_section_week_pair_corr_mean": aggregate_mean,
                "cross_section_week_pair_corr_median": aggregate_median,
                "cross_section_week_pairs": len(pair_correlations),
            }
        )
    return pl.DataFrame(rows)


def build_census(
    funding: pl.DataFrame, coverage_by_market: dict[str, str]
) -> pl.DataFrame:
    """Filter by funding coverage ground truth and compute the census core."""

    invalid = set(coverage_by_market.values()) - VALID_COVERAGE_STATUSES
    if invalid:
        raise ValueError(f"invalid coverage statuses: {sorted(invalid)}")
    usable = {
        market
        for market, status in coverage_by_market.items()
        if status != "no_data"
    }
    filtered = funding.filter(pl.col("market").is_in(usable))
    if filtered.is_empty():
        return pl.DataFrame(
            schema={"market": pl.String, "coverage_status": pl.String}
        )
    stats = compute_market_stats(filtered)
    persistence = compute_weekly_rank_persistence(filtered)
    coverage = pl.DataFrame(
        {
            "market": list(coverage_by_market),
            "coverage_status": list(coverage_by_market.values()),
        }
    )
    return (
        stats.join(persistence, on="market", how="left", validate="1:1")
        .join(coverage, on="market", how="left", validate="1:1")
        .with_columns(
            pl.when(
                pl.col("week_over_week_rank_corr").is_null()
                | pl.col("shock_half_life_hours").is_null()
            )
            .then(pl.lit("insufficient"))
            .when(
                (pl.col("week_over_week_rank_corr") >= 0.5)
                & (pl.col("shock_half_life_hours") >= 24.0)
            )
            .then(pl.lit("carry"))
            .otherwise(pl.lit("measured_fail"))
            .alias("carry_evidence")
        )
        .with_columns(
            (pl.col("carry_evidence") == "carry").alias("carry_relevant")
        )
    )


def build_capacity_map(census: pl.DataFrame, snapshots: pl.DataFrame) -> pl.DataFrame:
    """Join current snapshot size and expose two explicitly unitized products."""

    snapshot_size = snapshots.select(
        "market",
        pl.col("openInterest").cast(pl.Float64).alias("open_interest_base"),
        pl.col("oraclePx").cast(pl.Float64).alias("oracle_price_usd"),
        pl.col("dayNtlVlm").cast(pl.Float64).alias("day_ntl_vlm_usd"),
    ).with_columns(
        (pl.col("open_interest_base") * pl.col("oracle_price_usd")).alias(
            "open_interest_notional_usd"
        )
    )
    return (
        census.join(snapshot_size, on="market", how="left", validate="1:1")
        .with_columns(
            (pl.col("mean_apr") * pl.col("open_interest_notional_usd")).alias(
                "mean_apr_x_open_interest_notional_usd"
            ),
            (pl.col("mean_apr") * pl.col("day_ntl_vlm_usd")).alias(
                "mean_apr_x_day_ntl_vlm_usd"
            ),
        )
        .sort("mean_apr_x_day_ntl_vlm_usd", descending=True, nulls_last=True)
    )


def add_mean_apr_bootstrap_cis(
    census: pl.DataFrame, funding: pl.DataFrame
) -> pl.DataFrame:
    """Attach the pre-registered market x UTC-six-hour mean-APR interval."""

    rows: list[dict[str, object]] = []
    census_markets = set(census["market"].to_list())
    projected = funding.select("market", "time_exchange", "funding_rate").filter(
        pl.col("market").is_in(census_markets)
    )
    for market in census["market"].to_list():
        group = projected.filter(pl.col("market") == market).with_columns(
            (pl.col("funding_rate") * APR_FACTOR).alias("apr"),
            pl.col("time_exchange").dt.truncate("6h").alias("cluster_key"),
        )
        ci = cluster_bootstrap_ci(group, value_col="apr")
        rows.append(
            {
                "market": market,
                "mean_apr_ci_low": ci.ci_low,
                "mean_apr_ci_high": ci.ci_high,
                "mean_apr_bootstrap_n": ci.n,
                "mean_apr_bootstrap_G": ci.G,
                "mean_apr_ci_insufficient_clusters": ci.low_cluster,
                "bootstrap_resamples": 2_000,
                "bootstrap_seed": 0,
                "bootstrap_min_clusters": 5,
            }
        )
    return census.join(pl.DataFrame(rows), on="market", how="left", validate="1:1")


def build_frozen_universe(
    census: pl.DataFrame,
    snapshots: pl.DataFrame,
    *,
    liquidity_floor_usd: float = LIQUIDITY_FLOOR_USD,
) -> pl.DataFrame:
    """Return the stable, self-describing T3 universe contract."""

    if not math.isfinite(liquidity_floor_usd) or liquidity_floor_usd < 0:
        raise ValueError("liquidity_floor_usd must be finite and non-negative")
    capacity = build_capacity_map(census, snapshots).filter(
        pl.col("market").str.contains(":", literal=True)
    )
    return capacity.select(
        "market",
        "coverage_status",
        (pl.col("day_ntl_vlm_usd") > liquidity_floor_usd)
        .fill_null(False)
        .alias("passes_liquidity_floor"),
        pl.lit(float(liquidity_floor_usd)).alias("liquidity_floor_usd"),
        "carry_relevant",
        "carry_evidence",
        "mean_apr",
        "open_interest_base",
        "open_interest_notional_usd",
        "day_ntl_vlm_usd",
    ).sort("market")


def _lag_autocorrelation(
    values: Sequence[float],
    lag: int,
    times: Sequence[datetime] | None = None,
) -> float | None:
    pairs = _lagged_pairs(values, lag, times)
    return _pearson(
        [left for left, _ in pairs], [right for _, right in pairs]
    )


def _lagged_pairs(
    values: Sequence[float | None],
    lag: int,
    times: Sequence[datetime] | None = None,
) -> list[tuple[float, float]]:
    if lag < 1:
        raise ValueError("lag must be positive")
    if times is not None and len(values) != len(times):
        raise ValueError("values and times must have equal lengths")
    pairs: list[tuple[float, float]] = []
    for left_index in range(len(values) - lag):
        right_index = left_index + lag
        left = values[left_index]
        right = values[right_index]
        if left is None or right is None:
            continue
        left_value = float(left)
        right_value = float(right)
        if not math.isfinite(left_value) or not math.isfinite(right_value):
            continue
        if times is not None and any(
            not 0.0
            < (times[index + 1] - times[index]).total_seconds()
            <= MAX_CONSECUTIVE_GAP_SECONDS
            for index in range(left_index, right_index)
        ):
            continue
        pairs.append((left_value, right_value))
    return pairs


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    x_mean = sum(left) / len(left)
    y_mean = sum(right) / len(right)
    x_ss = sum((value - x_mean) ** 2 for value in left)
    y_ss = sum((value - y_mean) ** 2 for value in right)
    if x_ss == 0.0 or y_ss == 0.0:
        return None
    covariance = sum(
        (x - x_mean) * (y - y_mean) for x, y in zip(left, right, strict=True)
    )
    return covariance / math.sqrt(x_ss * y_ss)


def _average_ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        average = (start + 1 + end) / 2.0
        for index in order[start:end]:
            ranks[index] = average
        start = end
    return ranks


def _regime_lengths(
    apr_values: Sequence[float], times: Sequence[datetime], threshold: float
) -> list[int]:
    lengths: list[int] = []
    current = 0
    prior_time: datetime | None = None
    for apr, timestamp in zip(apr_values, times, strict=True):
        consecutive = (
            prior_time is None
            or 0.0
            < (timestamp - prior_time).total_seconds()
            <= MAX_CONSECUTIVE_GAP_SECONDS
        )
        if apr > threshold:
            if current and not consecutive:
                lengths.append(current)
                current = 0
            current += 1
        elif current:
            lengths.append(current)
            current = 0
        prior_time = timestamp
    if current:
        lengths.append(current)
    return lengths
