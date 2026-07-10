"""Causal funding-to-proxy-forced-flow linkage measurements for Study 3 S-F."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta
import math

import polars as pl

from charybdis.forced_flow import EVENT_SCHEMA
from charybdis.markout import cluster_bootstrap_statistic


LOW_BUCKET = "negative"
HIGH_BUCKET = "ge_100pct"
BUCKET_ORDER = (LOW_BUCKET, "0_to_25pct", "25_to_100pct", HIGH_BUCKET)
PROXY_WALLET_DTYPE = EVENT_SCHEMA["wallets"]


def add_sign_size_deciles(exposure: pl.DataFrame) -> pl.DataFrame:
    """Add sign × absolute-APR deciles weighted by market-hours of exposure."""

    required = {"annualized_rate", "exposure_hours"}
    missing = sorted(required - set(exposure.columns))
    if missing:
        raise ValueError(f"exposure missing required columns: {missing}")
    weights = [float(value) for value in exposure["exposure_hours"].to_list()]
    rates = [float(value) for value in exposure["annualized_rate"].to_list()]
    if any(weight <= 0.0 or not math.isfinite(weight) for weight in weights):
        raise ValueError("exposure hours must be finite and positive")
    if any(not math.isfinite(rate) for rate in rates):
        raise ValueError("annualized rates must be finite")
    total = sum(weights)
    labels = [""] * exposure.height
    cumulative = 0.0
    for index in sorted(range(exposure.height), key=lambda item: (abs(rates[item]), item)):
        midpoint = cumulative + weights[index] / 2.0
        decile = min(10, int(midpoint / total * 10.0) + 1)
        sign = "negative" if rates[index] < 0.0 else "nonnegative"
        labels[index] = f"{sign}_D{decile:02d}"
        cumulative += weights[index]
    return exposure.with_columns(pl.Series("sign_size_decile", labels, dtype=pl.String))


def _six_hour_block(timestamp: datetime) -> datetime:
    return timestamp.replace(
        hour=(timestamp.hour // 6) * 6,
        minute=0,
        second=0,
        microsecond=0,
    )


def build_exposure_panel(
    funding: pl.DataFrame,
    events: pl.DataFrame,
    *,
    window_start: datetime,
    window_end: datetime,
) -> pl.DataFrame:
    """Build causal funding exposure slices split at UTC-six-hour blocks."""

    if window_end <= window_start:
        raise ValueError("window_end must be after window_start")
    funding_required = {"market", "time_exchange", "funding_rate"}
    event_required = {"market", "start_time"}
    missing_funding = sorted(funding_required - set(funding.columns))
    missing_events = sorted(event_required - set(events.columns))
    if missing_funding:
        raise ValueError(f"funding missing required columns: {missing_funding}")
    if missing_events:
        raise ValueError(f"events missing required columns: {missing_events}")

    event_times = {
        market: sorted(group["start_time"].to_list())
        for (market,), group in events.partition_by("market", as_dict=True).items()
    }
    rows: list[dict[str, object]] = []
    for (market,), group in funding.sort(["market", "time_exchange"]).partition_by(
        "market", as_dict=True
    ).items():
        times = group["time_exchange"].to_list()
        rates = [float(value) for value in group["funding_rate"].to_list()]
        if bisect_right(times, window_start) == 0:
            raise ValueError(f"no funding settlement known by window start for {market!r}")
        changes = [
            window_start,
            *[time for time in times if window_start < time < window_end],
            window_end,
        ]
        market_events = event_times.get(market, [])
        for interval_start, interval_end in zip(changes, changes[1:]):
            rate_index = bisect_right(times, interval_start) - 1
            rate = rates[rate_index]
            cursor = interval_start
            while cursor < interval_end:
                block_start = _six_hour_block(cursor)
                stop = min(interval_end, block_start + timedelta(hours=6))
                count = bisect_left(market_events, stop) - bisect_left(
                    market_events, cursor
                )
                rows.append(
                    {
                        "market": market,
                        "block_start": block_start,
                        "interval_start": cursor,
                        "interval_end": stop,
                        "funding_rate": rate,
                        "annualized_rate": rate * 24.0 * 365.0,
                        "funding_bucket": funding_bucket(rate),
                        "exposure_hours": (stop - cursor).total_seconds() / 3600.0,
                        "event_count": count,
                        "cluster_key": f"{market}|{block_start.isoformat()}",
                    }
                )
                cursor = stop
    if not rows:
        raise ValueError("exposure panel is empty")
    return pl.DataFrame(rows).sort(["market", "interval_start"])


def wallet_bridge(
    events: pl.DataFrame,
    *,
    window_end: datetime | None = None,
    min_forward_window: timedelta = timedelta(hours=24),
) -> tuple[pl.DataFrame, dict[str, object]]:
    """Compare high-APR BUY-wallet reappearance with uncensored controls.

    ``wallets`` is the repeated-``user_taker`` list created by
    :mod:`charybdis.forced_flow`; importing its schema keeps this bridge tied to
    that detector's wallet representation instead of redefining wallet tags.
    """

    required = {"market", "start_time", "direction", "wallets", "funding_bucket"}
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f"events missing required columns: {missing}")
    if events.schema["wallets"] != PROXY_WALLET_DTYPE:
        raise ValueError("events wallets must use the forced-flow proxy wallet-list schema")
    if min_forward_window < timedelta(0):
        raise ValueError("min_forward_window must be nonnegative")
    if events.is_empty() and window_end is None:
        raise ValueError("window_end is required when events is empty")
    observed_end = window_end or events["start_time"].max()
    eligibility_cutoff = observed_end - min_forward_window

    appearances: dict[str, list[tuple[object, str]]] = {}
    cohorts: dict[str, dict[str, tuple[object, str]]] = {
        "high_apr_buy": {},
        "low_apr_buy": {},
        "high_apr_sell": {},
        "proxy_population": {},
    }
    for row in events.sort(["start_time", "market"]).iter_rows(named=True):
        for wallet in row["wallets"] or []:
            appearances.setdefault(wallet, []).append((row["start_time"], row["market"]))
            cohorts["proxy_population"].setdefault(
                wallet, (row["start_time"], row["market"])
            )
            if (
                row["funding_bucket"] == HIGH_BUCKET
                and row["direction"] == "BUY"
            ):
                cohorts["high_apr_buy"].setdefault(
                    wallet, (row["start_time"], row["market"])
                )
            if (
                row["funding_bucket"] in {LOW_BUCKET, "0_to_25pct"}
                and row["direction"] == "BUY"
            ):
                cohorts["low_apr_buy"].setdefault(
                    wallet, (row["start_time"], row["market"])
                )
            if (
                row["funding_bucket"] == HIGH_BUCKET
                and row["direction"] == "SELL"
            ):
                cohorts["high_apr_sell"].setdefault(
                    wallet, (row["start_time"], row["market"])
                )

    def eligible_reappearances(
        cohort: dict[str, tuple[object, str]],
    ) -> tuple[list[tuple[str, object, str, tuple[object, str] | None]], int]:
        eligible = []
        censored = 0
        for wallet, (cohort_time, cohort_market) in sorted(cohort.items()):
            if cohort_time > eligibility_cutoff:
                censored += 1
                continue
            later = next(
                (
                    (timestamp, market)
                    for timestamp, market in appearances[wallet]
                    if timestamp > cohort_time
                ),
                None,
            )
            eligible.append((wallet, cohort_time, cohort_market, later))
        return eligible, censored

    rows: list[dict[str, object]] = []
    cohort_results: dict[str, tuple[int, int, int, float]] = {}
    for cohort_name, cohort in cohorts.items():
        eligible, censored = eligible_reappearances(cohort)
        later_count = sum(later is not None for _, _, _, later in eligible)
        fraction = later_count / len(eligible) if eligible else math.nan
        cohort_results[cohort_name] = (len(eligible), later_count, censored, fraction)
    for wallet, cohort_time, cohort_market, later in eligible_reappearances(
        cohorts["high_apr_buy"]
    )[0]:
        rows.append(
            {
                "wallet": wallet,
                "cohort_market": cohort_market,
                "first_high_regime_long_time": cohort_time,
                "appeared_in_later_burst": later is not None,
                "first_later_burst_time": None if later is None else later[0],
                "first_later_burst_market": None if later is None else later[1],
            }
        )
    detail = pl.DataFrame(
        rows,
        schema={
            "wallet": pl.String,
            "cohort_market": pl.String,
            "first_high_regime_long_time": pl.Datetime("ns"),
            "appeared_in_later_burst": pl.Boolean,
            "first_later_burst_time": pl.Datetime("ns"),
            "first_later_burst_market": pl.String,
        },
    )
    cohort_count, later_count, censored_count, bridge_fraction = cohort_results[
        "high_apr_buy"
    ]
    low_count, _, _, low_fraction = cohort_results["low_apr_buy"]
    sell_count, _, _, sell_fraction = cohort_results["high_apr_sell"]
    population_count, _, _, population_fraction = cohort_results["proxy_population"]
    bridge_difference = bridge_fraction - low_fraction
    if cohort_count and low_count:
        standard_error = math.sqrt(
            bridge_fraction * (1.0 - bridge_fraction) / cohort_count
            + low_fraction * (1.0 - low_fraction) / low_count
        )
        within_noise = abs(bridge_difference) <= 1.96 * standard_error
    else:
        within_noise = False
    return detail, {
        "high_regime_long_accumulator_wallets": cohort_count,
        "later_burst_taker_wallets": later_count,
        "right_censored_high_regime_long_wallets": censored_count,
        "bridge_fraction": bridge_fraction,
        "low_apr_buy_control_wallets": low_count,
        "low_apr_buy_control_fraction": low_fraction,
        "high_apr_sell_control_wallets": sell_count,
        "high_apr_sell_control_fraction": sell_fraction,
        "proxy_population_control_wallets": population_count,
        "proxy_population_control_fraction": population_fraction,
        "bridge_minus_low_apr_buy": bridge_fraction - low_fraction,
        "bridge_minus_high_apr_sell": bridge_fraction - sell_fraction,
        "bridge_minus_proxy_population": bridge_fraction - population_fraction,
        "bridge_signal_difference": bridge_difference,
        "funding_specific_linkage": not within_noise,
        "min_forward_window_hours": min_forward_window.total_seconds() / 3600.0,
    }


def funding_bucket(hourly_rate: float) -> str:
    """Bucket an hourly settlement rate by simple annualized rate (rate × 8,760)."""

    apr = float(hourly_rate) * 24.0 * 365.0
    if apr < 0.0:
        return LOW_BUCKET
    if apr < 0.25:
        return "0_to_25pct"
    if apr < 1.0:
        return "25_to_100pct"
    return HIGH_BUCKET


def causal_conditioning_buckets(
    funding: pl.DataFrame,
    conditioning_times: pl.DataFrame,
) -> pl.DataFrame:
    """Label each time using the latest same-market settlement known by then."""

    funding_required = {"market", "time_exchange", "funding_rate"}
    time_required = {"market", "conditioning_time"}
    missing_funding = sorted(funding_required - set(funding.columns))
    missing_times = sorted(time_required - set(conditioning_times.columns))
    if missing_funding:
        raise ValueError(f"funding missing required columns: {missing_funding}")
    if missing_times:
        raise ValueError(f"conditioning times missing required columns: {missing_times}")

    histories: dict[str, tuple[list[object], list[float]]] = {}
    for (market,), group in funding.sort(["market", "time_exchange"]).partition_by(
        "market", as_dict=True
    ).items():
        histories[market] = (
            group["time_exchange"].to_list(),
            [float(value) for value in group["funding_rate"].to_list()],
        )
    rows: list[dict[str, object]] = []
    for row in conditioning_times.iter_rows(named=True):
        history = histories.get(row["market"])
        if history is None:
            raise ValueError(f"no funding history for market {row['market']!r}")
        times, rates = history
        index = bisect_right(times, row["conditioning_time"]) - 1
        if index < 0:
            raise ValueError(
                f"no funding settlement known by {row['conditioning_time']!r} "
                f"for market {row['market']!r}"
            )
        rate = rates[index]
        rows.append(
            {
                "market": row["market"],
                "conditioning_time": row["conditioning_time"],
                "funding_settlement_time": times[index],
                "funding_rate": rate,
                "annualized_rate": rate * 24.0 * 365.0,
                "funding_bucket": funding_bucket(rate),
            }
        )
    return pl.DataFrame(rows)


def hazard_table(
    conditioning: pl.DataFrame,
    events: pl.DataFrame,
    *,
    horizon: timedelta = timedelta(hours=24),
) -> pl.DataFrame:
    """Return P(same-market event in ``(t, t+horizon]``) by funding bucket."""

    condition_required = {"market", "conditioning_time", "funding_bucket"}
    event_required = {"market", "start_time"}
    missing_condition = sorted(condition_required - set(conditioning.columns))
    missing_events = sorted(event_required - set(events.columns))
    if missing_condition:
        raise ValueError(f"conditioning missing required columns: {missing_condition}")
    if missing_events:
        raise ValueError(f"events missing required columns: {missing_events}")
    if horizon <= timedelta(0):
        raise ValueError("horizon must be positive")

    event_times = {
        market: sorted(group["start_time"].to_list())
        for (market,), group in events.partition_by("market", as_dict=True).items()
    }
    labeled: list[dict[str, object]] = []
    for row in conditioning.iter_rows(named=True):
        times = event_times.get(row["market"], [])
        start = bisect_right(times, row["conditioning_time"])
        stop = bisect_right(times, row["conditioning_time"] + horizon)
        labeled.append(
            {
                "funding_bucket": row["funding_bucket"],
                "event_within_24h": stop > start,
            }
        )
    if not labeled:
        return pl.DataFrame(
            schema={
                "funding_bucket": pl.String,
                "conditioning_observations": pl.Int64,
                "event_within_horizon_count": pl.Int64,
                "probability_event_within_horizon": pl.Float64,
                "hazard_horizon_hours": pl.Float64,
                "coverage_saturated": pl.Boolean,
                "event_within_24h_count": pl.Int64,
                "probability_event_within_24h": pl.Float64,
            }
        )
    result = (
        pl.DataFrame(labeled)
        .group_by("funding_bucket")
        .agg(
            pl.len().alias("conditioning_observations"),
            pl.col("event_within_24h").sum().alias("event_within_horizon_count"),
            pl.col("event_within_24h").mean().alias(
                "probability_event_within_horizon"
            ),
        )
        .with_columns(
            pl.lit(horizon.total_seconds() / 3600.0).alias("hazard_horizon_hours"),
            (pl.col("probability_event_within_horizon") >= 0.9).alias(
                "coverage_saturated"
            ),
            pl.col("event_within_horizon_count").alias("event_within_24h_count"),
            pl.col("probability_event_within_horizon").alias(
                "probability_event_within_24h"
            ),
        )
        .sort("funding_bucket")
    )
    return result


def _event_rate(frame: pl.DataFrame) -> float:
    exposure = float(frame["exposure_hours"].sum())
    if exposure <= 0.0:
        return math.nan
    return float(frame["event_count"].sum()) / exposure


def _high_low_ratio(frame: pl.DataFrame) -> float:
    high = frame.filter(pl.col("funding_bucket") == HIGH_BUCKET)
    low = frame.filter(pl.col("funding_bucket") == LOW_BUCKET)
    high_rate = _event_rate(high)
    low_rate = _event_rate(low)
    if not math.isfinite(high_rate) or not math.isfinite(low_rate) or low_rate == 0.0:
        return math.nan
    return high_rate / low_rate


def market_clustered_rate_ratio(
    exposure: pl.DataFrame,
    *,
    n_resamples: int = 2_000,
    seed: int = 0,
    min_clusters: int = 5,
) -> dict[str, object]:
    """Diagnose the pooled high/low ratio with whole markets as clusters."""

    required = {
        "market",
        "funding_bucket",
        "exposure_hours",
        "event_count",
    }
    missing = sorted(required - set(exposure.columns))
    if missing:
        raise ValueError(f"exposure missing required columns: {missing}")
    result = cluster_bootstrap_statistic(
        exposure.filter(pl.col("funding_bucket").is_in([LOW_BUCKET, HIGH_BUCKET])),
        statistic=_high_low_ratio,
        cluster_col="market",
        n_resamples=n_resamples,
        seed=seed,
        min_clusters=min_clusters,
    )
    return {
        "rate_ratio": result.point_estimate,
        "ci_low": result.ci_low,
        "ci_high": result.ci_high,
        "clusters": result.G,
        "low_cluster": result.low_cluster,
        "evidence_status": "insufficient_evidence" if result.low_cluster else "estimable",
    }


def summarize_event_rates(
    exposure: pl.DataFrame,
    *,
    n_resamples: int = 2_000,
    seed: int = 0,
    min_clusters: int = 5,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Summarize events per market-hour and the >=100%/negative rate ratio.

    Input rows are exposure slices already split at market × UTC-six-hour
    cluster boundaries. ``event_count`` is the number of events in that slice.
    The imported Study-1 cluster resampler therefore preserves both numerator
    and exposure-time denominator within each sampled cluster.
    """

    required = {
        "funding_bucket",
        "exposure_hours",
        "event_count",
        "cluster_key",
    }
    missing = sorted(required - set(exposure.columns))
    if missing:
        raise ValueError(f"exposure missing required columns: {missing}")
    if exposure.is_empty():
        raise ValueError("exposure must not be empty")

    rates = summarize_bucket_rates(
        exposure,
        n_resamples=n_resamples,
        seed=seed,
        min_clusters=min_clusters,
    )

    ratio_rows: list[dict[str, object]] = []
    scopes: list[tuple[str, pl.DataFrame]] = [("ALL", exposure)]
    if "market" in exposure.columns:
        scopes.extend(
            (market, exposure.filter(pl.col("market") == market))
            for market in sorted(exposure["market"].unique().to_list())
        )
    for offset, (scope, scoped) in enumerate(scopes):
        ratio_ci = cluster_bootstrap_statistic(
            scoped.filter(pl.col("funding_bucket").is_in([LOW_BUCKET, HIGH_BUCKET])),
            statistic=_high_low_ratio,
            n_resamples=n_resamples,
            seed=seed + 1 + offset,
            min_clusters=min_clusters,
        )
        ratio_rows.append(
            {
                "scope": scope,
                "numerator_bucket": HIGH_BUCKET,
                "denominator_bucket": LOW_BUCKET,
                "rate_ratio": ratio_ci.point_estimate,
                "ci_low": ratio_ci.ci_low,
                "ci_high": ratio_ci.ci_high,
                "clusters": ratio_ci.G,
                "low_cluster": ratio_ci.low_cluster,
            }
        )
    return rates, pl.DataFrame(ratio_rows)


def summarize_bucket_rates(
    exposure: pl.DataFrame,
    *,
    n_resamples: int = 2_000,
    seed: int = 0,
    min_clusters: int = 5,
) -> pl.DataFrame:
    """Cluster-bootstrap event rates for arbitrary labels in funding_bucket."""

    required = {
        "funding_bucket",
        "exposure_hours",
        "event_count",
        "cluster_key",
    }
    missing = sorted(required - set(exposure.columns))
    if missing:
        raise ValueError(f"exposure missing required columns: {missing}")
    if exposure.is_empty():
        raise ValueError("exposure must not be empty")
    rows: list[dict[str, object]] = []
    for bucket in exposure["funding_bucket"].unique(maintain_order=True).to_list():
        group = exposure.filter(pl.col("funding_bucket") == bucket)
        ci = cluster_bootstrap_statistic(
            group,
            statistic=_event_rate,
            n_resamples=n_resamples,
            seed=seed,
            min_clusters=min_clusters,
        )
        rows.append(
            {
                "funding_bucket": bucket,
                "event_count": int(group["event_count"].sum()),
                "exposure_hours": float(group["exposure_hours"].sum()),
                "event_rate_per_market_hour": ci.point_estimate,
                "ci_low": ci.ci_low,
                "ci_high": ci.ci_high,
                "clusters": ci.G,
                "low_cluster": ci.low_cluster,
            }
        )
    return pl.DataFrame(rows).sort("funding_bucket")
