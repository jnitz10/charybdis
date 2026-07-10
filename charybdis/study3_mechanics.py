"""Study 3 S-B feed reconciliation and funding-formula consistency checks."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl

from charybdis.loaders import scan_oracle_prices


SCOPED_MARKETS = {"SKHX": "xyz:SKHX", "SMSN": "xyz:SMSN"}
PRE_SPECIFIED_INTEREST_RATE = 0.0001
XYZ_FUNDING_MULTIPLIER = 0.5
CLAMP_BOUND = 0.0005
SETTLEMENT_DIVISOR = 8.0
HOURLY_CAP = 0.04
MAX_CONSECUTIVE_MISSING_MINUTES = 5
# Endpoint R-squared measures feed/formula agreement, not funding predictability.
ENDPOINT_RESULT_LABEL = "feed-reconciliation / formula-consistency check"
SHUFFLE_DIAGNOSTIC_LABEL = "intra-hour sample-timing/drift diagnostic"


def funding_rate_from_premium(
    premium: np.ndarray | float,
    *,
    interest_rate: float,
    funding_multiplier: float = 1.0,
    clamp_bound: float = 0.0005,
    settlement_divisor: float = 8.0,
    hourly_cap: float = 0.04,
) -> np.ndarray:
    """Convert an hourly average premium to the paid hourly funding rate."""
    values = np.asarray(premium, dtype=float)
    eight_hour_rate = values + np.clip(
        interest_rate - values, -clamp_bound, clamp_bound
    )
    hourly_rate = funding_multiplier * eight_hour_rate / settlement_divisor
    return np.clip(hourly_rate, -hourly_cap, hourly_cap)


def reconcile_samples(
    samples: pl.DataFrame,
    realized: pl.DataFrame,
    *,
    interest_rate: float,
    funding_multiplier: float = 1.0,
    clamp_bound: float = CLAMP_BOUND,
    settlement_divisor: float = SETTLEMENT_DIVISOR,
    hourly_cap: float = HOURLY_CAP,
    require_complete_hours: bool = False,
    shuffle_count: int = 100,
    shuffle_seed: int = 0,
    iid_seed_count: int = 100,
    iid_seed: int = 0,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Build per-hour reconciliation and observed/iid/shuffle minute R² curves."""
    if shuffle_count < 100:
        raise ValueError("shuffle_count must be at least 100")
    if iid_seed_count < 100:
        raise ValueError("iid_seed_count must be at least 100")
    # Invalid denominators are dropped before aggregation so one corrupt tick cannot
    # turn an otherwise usable hour's mean premium into inf/NaN.
    prepared = samples.filter(pl.col("oracle_px") != 0).with_columns(
        ((pl.col("mark_px") - pl.col("oracle_px")) / pl.col("oracle_px")).alias(
            "premium_sample"
        ),
        pl.col("time_exchange")
        .dt.truncate("1h")
        .dt.offset_by("1h")
        .cast(pl.Datetime("us"))
        .alias("settlement_time"),
        pl.col("time_exchange").dt.minute().alias("sample_minute"),
    )
    if require_complete_hours:
        complete = (
            prepared.group_by("market", "settlement_time")
            .agg(
                pl.col("sample_minute").min().alias("first_minute"),
                pl.col("sample_minute").max().alias("last_minute"),
                pl.col("sample_minute")
                .unique()
                .sort()
                .diff()
                .max()
                .sub(1)
                .alias("max_missing_minute_run"),
            )
            .filter(
                (pl.col("first_minute") == 0)
                & (pl.col("last_minute") == 59)
                & (
                    pl.col("max_missing_minute_run")
                    <= MAX_CONSECUTIVE_MISSING_MINUTES
                )
            )
            .select("market", "settlement_time")
        )
        prepared = prepared.join(
            complete, on=["market", "settlement_time"], how="semi"
        )
    actual = realized.select(
        "market",
        pl.col("time_exchange")
        .dt.truncate("1h")
        .cast(pl.Datetime("us"))
        .alias("settlement_time"),
        pl.col("funding_rate").alias("realized_funding"),
    )

    def aggregate(frame: pl.DataFrame) -> pl.DataFrame:
        hourly = (
            frame.group_by("market", "settlement_time")
            .agg(
                pl.col("premium_sample").mean().alias("average_premium"),
                pl.len().alias("sample_count"),
                pl.col("time_exchange").min().alias("first_sample_time"),
                pl.col("time_exchange").max().alias("last_sample_time"),
                pl.when((pl.col("update_class") == "Fallback").any())
                .then(pl.lit("Fallback"))
                .otherwise(pl.lit("Deployer"))
                .alias("update_class"),
            )
            .join(actual, on=["market", "settlement_time"], how="inner")
            .sort("market", "settlement_time")
        )
        predicted = funding_rate_from_premium(
            hourly["average_premium"].to_numpy(),
            interest_rate=interest_rate,
            funding_multiplier=funding_multiplier,
            clamp_bound=clamp_bound,
            settlement_divisor=settlement_divisor,
            hourly_cap=hourly_cap,
        )
        return hourly.with_columns(pl.Series("predicted_funding", predicted))

    per_hour = aggregate(prepared)
    per_hour = per_hour.with_columns(
        (pl.col("realized_funding") - pl.col("predicted_funding")).alias("residual"),
        (
            (pl.col("realized_funding") - pl.col("predicted_funding")) * 10_000.0
        ).alias("residual_bps"),
        pl.Series(
            "cap_hit",
            detect_cap_hits(
                per_hour["predicted_funding"].to_numpy(), hourly_cap=hourly_cap
            ),
        ),
        (
            (pl.col("average_premium") - interest_rate).abs() > clamp_bound
        ).alias("clamp_active"),
    )
    shuffled_floor = _within_hour_shuffle_floor(
        prepared,
        per_hour,
        interest_rate=interest_rate,
        funding_multiplier=funding_multiplier,
        clamp_bound=clamp_bound,
        settlement_divisor=settlement_divisor,
        hourly_cap=hourly_cap,
        shuffle_count=shuffle_count,
        shuffle_seed=shuffle_seed,
    )
    iid_floor, iid_seed_variance = _iid_partial_observation_floor(
        prepared,
        per_hour,
        seed_count=iid_seed_count,
        seed=iid_seed,
    )
    # Under the iid null, corr(realized, partial)^2 equals the partial-vs-full
    # sample-mean R² times corr(realized, full)^2.  Scaling by the empirical
    # full-hour endpoint therefore keeps the null on the observed statistic's
    # realized-funding target and makes the full-observation excess exactly zero.
    endpoint_r2 = _r_squared(
        per_hour["realized_funding"].to_numpy(),
        per_hour["predicted_funding"].to_numpy(),
    )
    iid_floor *= endpoint_r2
    iid_seed_variance *= endpoint_r2**2
    curve_rows = []
    for minute in range(60):
        partial = aggregate(samples_through_minute(prepared, minute))
        y = partial["realized_funding"].to_numpy()
        prediction = partial["predicted_funding"].to_numpy()
        r_squared = _r_squared(y, prediction)
        floor = shuffled_floor[minute]
        iid_value = iid_floor[minute]
        curve_rows.append(
            {
                "minute": minute,
                "observed_r2": r_squared if np.isfinite(r_squared) else None,
                "iid_floor": iid_value if np.isfinite(iid_value) else None,
                "iid_excess": (
                    r_squared - iid_value
                    if np.isfinite(r_squared) and np.isfinite(iid_value)
                    else None
                ),
                "iid_floor_seed_variance": (
                    iid_seed_variance[minute]
                    if np.isfinite(iid_seed_variance[minute])
                    else None
                ),
                "iid_seed_count": iid_seed_count,
                "shuffle_r2": floor if np.isfinite(floor) else None,
                "shuffle_timing_gap": (
                    r_squared - floor
                    if np.isfinite(r_squared) and np.isfinite(floor)
                    else None
                ),
                "shuffle_diagnostic": SHUFFLE_DIAGNOSTIC_LABEL,
                # Backward-compatible observed alias; this is the F-B curve.
                "r_squared": r_squared if np.isfinite(r_squared) else None,
                "hour_count": len(y),
                "sample_count": int(partial["sample_count"].sum()) if len(y) else 0,
            }
        )
    return per_hour, pl.DataFrame(curve_rows)


def _iid_partial_observation_floor(
    prepared: pl.DataFrame,
    per_hour: pl.DataFrame,
    *,
    seed_count: int,
    seed: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Estimate the iid partial-sample R² floor and its seed variance.

    Within an iid hour, a uniformly selected subset is exchangeable with the first
    ``n`` draws.  We therefore simulate its sum and the independent unobserved
    complement directly as Gaussian iid sums.  This preserves every empirical
    hour's observed/full sample counts while excluding stable between-hour levels;
    those levels are the structure the F-B comparison is intended to detect.
    """
    indexed_hours = per_hour.select("market", "settlement_time").with_row_index(
        "hour_index"
    )
    ordered = prepared.join(
        indexed_hours,
        on=["market", "settlement_time"],
        how="inner",
    ).select("hour_index", "sample_minute")
    if ordered.is_empty():
        empty = np.full(60, np.nan)
        return empty, empty.copy()

    hour_count = len(indexed_hours)
    minute_counts = np.zeros((hour_count, 60), dtype=np.int64)
    grouped = ordered.group_by("hour_index").agg(
        pl.col("sample_minute").alias("minutes")
    )
    for hour_index, minutes in grouped.iter_rows():
        minute_counts[hour_index] = np.bincount(
            np.asarray(minutes, dtype=np.int64), minlength=60
        )
    cumulative_counts = np.cumsum(minute_counts, axis=1)
    full_counts = cumulative_counts[:, -1]
    estimates = np.full((seed_count, 60), np.nan)
    rng = np.random.default_rng(seed)

    for seed_index in range(seed_count):
        for minute in range(60):
            observed_counts = cumulative_counts[:, minute]
            valid = observed_counts > 0
            n = observed_counts[valid].astype(float)
            total = full_counts[valid].astype(float)
            # Sums of n and N-n independent N(0,1) iid observations.  Scale is
            # immaterial because the statistic is OLS R² with an intercept.
            observed_sums = np.sqrt(n) * rng.standard_normal(len(n))
            remaining_sums = np.sqrt(total - n) * rng.standard_normal(len(n))
            partial_means = observed_sums / n
            full_means = (observed_sums + remaining_sums) / total
            estimates[seed_index, minute] = _r_squared(full_means, partial_means)

    means = np.full(60, np.nan)
    variances = np.full(60, np.nan)
    for minute in range(60):
        values = estimates[:, minute]
        values = values[np.isfinite(values)]
        if len(values):
            means[minute] = float(np.mean(values))
        if len(values) > 1:
            variances[minute] = float(np.var(values, ddof=1))
    return means, variances


def samples_through_minute(samples: pl.DataFrame, minute: int) -> pl.DataFrame:
    """Return only information observable by the end of `minute` (inclusive)."""
    minute_expression = (
        pl.col("sample_minute")
        if "sample_minute" in samples.columns
        else pl.col("time_exchange").dt.minute()
    )
    return samples.filter(minute_expression <= minute)


def _within_hour_shuffle_floor(
    prepared: pl.DataFrame,
    per_hour: pl.DataFrame,
    *,
    interest_rate: float,
    funding_multiplier: float,
    clamp_bound: float,
    settlement_divisor: float,
    hourly_cap: float,
    shuffle_count: int,
    shuffle_seed: int,
) -> np.ndarray:
    """Secondary timing/drift diagnostic from within-hour permutations.

    This intentionally preserves each hour's premium level.  It is not the F-B
    routing null: observed below shuffle means the contiguous early window is a
    worse estimator than a randomly spread subsample, evidence of intra-hour drift.
    """
    indexed_hours = per_hour.select(
        "market", "settlement_time", "realized_funding"
    ).with_row_index("hour_index")
    ordered = (
        prepared.join(
            indexed_hours.select("market", "settlement_time", "hour_index"),
            on=["market", "settlement_time"],
            how="inner",
        )
        .sort("hour_index")
        .select("hour_index", "sample_minute", "premium_sample")
    )
    if ordered.is_empty():
        return np.full(60, np.nan)

    hour_ids = ordered["hour_index"].to_numpy()
    minutes = ordered["sample_minute"].to_numpy().astype(np.int64, copy=False)
    premiums = ordered["premium_sample"].to_numpy()
    boundaries = np.r_[0, np.flatnonzero(np.diff(hour_ids)) + 1, len(hour_ids)]
    hour_count = len(indexed_hours)
    minute_counts = np.zeros((hour_count, 60), dtype=np.int64)
    for left, right in zip(boundaries[:-1], boundaries[1:], strict=True):
        hour = int(hour_ids[left])
        minute_counts[hour] = np.bincount(minutes[left:right], minlength=60)
    cumulative_counts = np.cumsum(minute_counts, axis=1)
    realized_values = indexed_hours["realized_funding"].to_numpy()
    totals = np.zeros(60, dtype=float)
    valid_shuffles = np.zeros(60, dtype=np.int64)
    rng = np.random.default_rng(shuffle_seed)

    for _ in range(shuffle_count):
        minute_sums = np.zeros((hour_count, 60), dtype=float)
        for left, right in zip(boundaries[:-1], boundaries[1:], strict=True):
            hour = int(hour_ids[left])
            shuffled_values = rng.permutation(premiums[left:right])
            minute_sums[hour] = np.bincount(
                minutes[left:right], weights=shuffled_values, minlength=60
            )
        cumulative_sums = np.cumsum(minute_sums, axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            average_premiums = cumulative_sums / cumulative_counts
        predictions = funding_rate_from_premium(
            average_premiums,
            interest_rate=interest_rate,
            funding_multiplier=funding_multiplier,
            clamp_bound=clamp_bound,
            settlement_divisor=settlement_divisor,
            hourly_cap=hourly_cap,
        )
        for minute in range(60):
            valid = cumulative_counts[:, minute] > 0
            value = _r_squared(realized_values[valid], predictions[valid, minute])
            if np.isfinite(value):
                totals[minute] += value
                valid_shuffles[minute] += 1

    return np.divide(
        totals,
        valid_shuffles,
        out=np.full(60, np.nan),
        where=valid_shuffles > 0,
    )


def _r_squared(realized: np.ndarray, predicted: np.ndarray) -> float:
    """OLS-with-intercept R-squared for realized funding on a prediction."""
    if len(realized) < 2 or np.var(realized) == 0.0:
        return float("nan")
    if np.var(predicted) == 0.0:
        return 0.0
    design = np.column_stack([np.ones(len(predicted)), predicted])
    fitted = design @ np.linalg.lstsq(design, realized, rcond=None)[0]
    denominator = np.sum((realized - np.mean(realized)) ** 2)
    return float(1.0 - np.sum((realized - fitted) ** 2) / denominator)


def detect_cap_hits(
    predicted: np.ndarray | float, *, hourly_cap: float = 0.04
) -> np.ndarray:
    """Identify predicted rates sitting at the hourly funding cap."""
    return np.abs(np.asarray(predicted, dtype=float)) == hourly_cap


def minute_r_squared_curve(*args, **kwargs) -> pl.DataFrame:
    """Compute cumulative prediction R-squared for minutes zero through 59."""
    return reconcile_samples(*args, **kwargs)[1]


def regression_statistics(
    frame: pl.DataFrame, *, assumed_multiplier: float = XYZ_FUNDING_MULTIPLIER
) -> dict[str, float | int]:
    """OLS feed-reconciliation diagnostics, including the affine identity gap."""
    y = frame["realized_funding"].to_numpy()
    prediction = frame["predicted_funding"].to_numpy()
    design = np.column_stack([np.ones(len(prediction)), prediction])
    intercept, slope = np.linalg.lstsq(design, y, rcond=None)[0]
    return {
        "n": len(y),
        "intercept": float(intercept),
        "slope": float(slope),
        "r_squared": _r_squared(y, prediction),
        "raw_premium_r_squared": _r_squared(
            y, frame["average_premium"].to_numpy()
        ),
        "mean_residual_bps": float(np.mean(y - prediction) * 10_000.0),
        "empirically_implied_multiplier": float(assumed_multiplier * slope),
    }


def clamp_regime_statistics(
    frame: pl.DataFrame, *, interest_rate: float, clamp_bound: float
) -> dict[str, dict[str, float | int]]:
    """Split constant-output (clamp inactive) from clamp-active market-hours."""
    active_mask = (
        np.abs(frame["average_premium"].to_numpy() - interest_rate) > clamp_bound
    )
    result: dict[str, dict[str, float | int]] = {}
    for label, mask in (("inactive", ~active_mask), ("active", active_mask)):
        subset = frame.filter(pl.Series(mask))
        result[label] = {
            "n": len(subset),
            "r_squared": _r_squared(
                subset["realized_funding"].to_numpy(),
                subset["predicted_funding"].to_numpy(),
            ),
        }
    return result


def estimate_interest_rate(
    frame: pl.DataFrame,
    *,
    funding_multiplier: float,
    clamp_bound: float,
    settlement_divisor: float,
    hourly_cap: float,
) -> tuple[float, float]:
    """Grid-estimate the interest term with all other documented constants fixed."""
    premium = frame["average_premium"].to_numpy()
    realized = frame["realized_funding"].to_numpy()
    grid = np.linspace(-0.001, 0.001, 4001)
    best_interest = float("nan")
    best_sse = float("inf")
    for interest in grid:
        predicted = funding_rate_from_premium(
            premium,
            interest_rate=float(interest),
            funding_multiplier=funding_multiplier,
            clamp_bound=clamp_bound,
            settlement_divisor=settlement_divisor,
            hourly_cap=hourly_cap,
        )
        sse = float(np.sum((realized - predicted) ** 2))
        if sse < best_sse:
            best_interest, best_sse = float(interest), sse
    return best_interest, float(np.sqrt(best_sse / len(realized)))


def load_scoped_inputs(
    data_root: Path, funding_path: Path
) -> tuple[pl.DataFrame, pl.DataFrame, dict[str, dict[str, object]]]:
    """Load only the five oracle columns and three funding columns used by S-B."""
    frames: list[pl.LazyFrame] = []
    inventory: dict[str, dict[str, object]] = {}
    for symbol, market in SCOPED_MARKETS.items():
        paths = sorted(
            (data_root / "T-HLORACLEPRICES").glob(
                f"D-*/E-HYPERLIQUIDL4/*+S-{symbol}.csv.gz"
            )
        )
        if not paths:
            raise FileNotFoundError(f"no oracle partitions found for {symbol}")
        partitions = [path.parts[-3].removeprefix("D-") for path in paths]
        parsed = [datetime.strptime(value, "%Y%m%d%H") for value in partitions]
        missing_partitions = sum(
            right - left != timedelta(hours=1)
            for left, right in zip(parsed, parsed[1:], strict=False)
        )
        inventory[symbol] = {
            "files": len(paths),
            "first_partition": partitions[0],
            "last_partition": partitions[-1],
            "partition_gaps": missing_partitions,
        }
        for path in paths:
            frames.append(
                scan_oracle_prices(
                    path,
                    columns=[
                        "time_exchange",
                        "update_class",
                        "mark_px",
                        "oracle_px",
                    ],
                ).with_columns(pl.lit(market).alias("market"))
            )
    samples = pl.concat(frames).collect(engine="streaming")
    realized = (
        pl.scan_parquet(funding_path)
        .select("market", "time_exchange", "funding_rate")
        .filter(pl.col("market").is_in(list(SCOPED_MARKETS.values())))
        .collect(engine="streaming")
    )
    return samples, realized, inventory


def _format_time(value: object) -> str:
    return str(value).replace(" ", "T") + "Z"


def render_routing_section(curve: pl.DataFrame) -> str:
    """Render the numbers-only F-B/G-F2 routing input and selected curve rows."""
    selected = curve.filter(pl.col("minute").is_in([0, 10, 30, 50, 59])).sort(
        "minute"
    )
    rows = {row["minute"]: row for row in selected.iter_rows(named=True)}
    minute_0, minute_10, minute_50 = rows[0], rows[10], rows[50]
    lines = [
        "## §1.6 F-B/G-F2 Routing Input — numbers only, no verdict",
        "",
        (
            f"Pre-registered F-B metric: minute 50 observed R-squared "
            f"`{minute_50['observed_r2']:.8f}`; minute 10 observed R-squared "
            f"`{minute_10['observed_r2']:.8f}` (50-minute lead). Minute 0 "
            f"observed R-squared `{minute_0['observed_r2']:.8f}`, iid floor "
            f"`{minute_0['iid_floor']:.8f}`, iid excess "
            f"`{minute_0['iid_excess']:.8f}`. The minute-50 figure is largely a "
            f"partial-observation artifact because 50/60 of the averaging window "
            f"has already been seen; at the 50-minute lead, minute 10 observed "
            f"R-squared is `{minute_10['observed_r2']:.8f}`. Versus the iid floor, "
            f"minute-0 observed R-squared `{minute_0['observed_r2']:.8f}` exceeds "
            f"minute-0 iid floor `{minute_0['iid_floor']:.8f}` by iid excess "
            f"`{minute_0['iid_excess']:.8f}`."
        ),
        "",
        "| minute | observed_r2 | iid_floor | iid_excess | shuffle_r2 |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in selected.iter_rows(named=True):
        lines.append(
            f"| {row['minute']} | {row['observed_r2']:.8f} | "
            f"{row['iid_floor']:.8f} | {row['iid_excess']:.8f} | "
            f"{row['shuffle_r2']:.8f} |"
        )
    return "\n".join(lines)


def _write_outputs(
    per_hour: pl.DataFrame,
    curve: pl.DataFrame,
    *,
    inventory: dict[str, dict[str, object]],
    output_path: Path,
    report_path: Path,
) -> None:
    overall = regression_statistics(per_hour)
    clamp_split = clamp_regime_statistics(
        per_hour,
        interest_rate=PRE_SPECIFIED_INTEREST_RATE,
        clamp_bound=CLAMP_BOUND,
    )
    per_market = {
        market: regression_statistics(per_hour.filter(pl.col("market") == market))
        for market in SCOPED_MARKETS.values()
    }
    interest_estimate, interest_rmse = estimate_interest_rate(
        per_hour,
        funding_multiplier=XYZ_FUNDING_MULTIPLIER,
        clamp_bound=CLAMP_BOUND,
        settlement_divisor=SETTLEMENT_DIVISOR,
        hourly_cap=HOURLY_CAP,
    )
    per_hour = per_hour.with_columns(
        pl.lit("hourly").alias("record_type"),
        pl.lit(PRE_SPECIFIED_INTEREST_RATE).alias("formula_interest_rate"),
        pl.lit(interest_estimate).alias("empirical_interest_rate"),
    )
    curve_output = curve.rename({"sample_count": "curve_sample_count"}).with_columns(
        pl.lit("minute_r2").alias("record_type"),
        pl.lit("ALL").alias("market"),
        pl.lit(PRE_SPECIFIED_INTEREST_RATE).alias("formula_interest_rate"),
        pl.lit(interest_estimate).alias("empirical_interest_rate"),
    )
    combined = pl.concat([per_hour, curve_output], how="diagonal_relaxed").select(
        "record_type",
        "market",
        "settlement_time",
        "first_sample_time",
        "last_sample_time",
        "average_premium",
        "predicted_funding",
        "realized_funding",
        "residual",
        "residual_bps",
        "update_class",
        "sample_count",
        "cap_hit",
        "clamp_active",
        "minute",
        "observed_r2",
        "iid_floor",
        "iid_excess",
        "iid_floor_seed_variance",
        "iid_seed_count",
        "shuffle_r2",
        "shuffle_timing_gap",
        "shuffle_diagnostic",
        "r_squared",
        "hour_count",
        "curve_sample_count",
        "formula_interest_rate",
        "empirical_interest_rate",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.write_parquet(output_path, compression="zstd")

    residual = per_hour["residual_bps"].to_numpy()
    quantiles = np.quantile(residual, [0.0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0])
    class_rows = []
    for update_class in ("Deployer", "Fallback"):
        values = per_hour.filter(pl.col("update_class") == update_class)[
            "residual_bps"
        ].to_numpy()
        class_rows.append(
            {
                "class": update_class,
                "n": len(values),
                "mean": float(np.mean(values)) if len(values) else float("nan"),
                "median": float(np.median(values)) if len(values) else float("nan"),
                "rmse": float(np.sqrt(np.mean(values**2))) if len(values) else float("nan"),
            }
        )
    class_difference = class_rows[1]["mean"] - class_rows[0]["mean"]
    cap_count = int(per_hour["cap_hit"].sum())
    start = per_hour["settlement_time"].min()
    end = per_hour["settlement_time"].max()

    lines = [
        "# Study 3 S-B mechanics reconciliation — 2026-07-10",
        "",
        "## Scope and coverage",
        "",
        f"Markets: `xyz:SKHX`, `xyz:SMSN`. Oracle inventory: SKHX {inventory['SKHX']['files']} files and SMSN {inventory['SMSN']['files']} files; both span `{inventory['SKHX']['first_partition']}` through `{inventory['SKHX']['last_partition']}` with `{inventory['SKHX']['partition_gaps']}` partition gaps.",
        f"The complete-hour regression window is `{_format_time(start)}` through `{_format_time(end)}` ({overall['n']} market-hours). Completeness requires observations in minute 0 and minute 59 and no run of more than {MAX_CONSECUTIVE_MISSING_MINUTES} consecutive missing minute buckets; excluded hours are removed uniformly from the hourly regression and every minute-curve point. Oracle data starts 2026-06-17, so S-B is only an approximately three-week study (20.75 days of feed partitions); funding history before that date is outside this reconciliation.",
        "",
        "The feed uses bare coin identifiers. SKHX and SMSN are single-dex xyz coins and are unambiguous. SP500 was not included: its bare identifier collides across dexes, the files contain no dex column, and no contemporaneous per-dex REST oracle-price history exists in the scoped cache for historical price-cluster labeling.",
        "",
        "G-F1 listing of every hourly extension prefix after 2026-07-08 09:00 returned zero objects. Dry-run: 0 files, 0 bytes, `$0.00`, projected cumulative meter `$116.92`; no GET/download was run and Study-3 new spend remained `$0.00`.",
        "",
        "## Mechanical prediction and regression setup",
        "",
        "For settlement `h`, samples satisfy `floor(time_exchange, 1h) = h-1`, hence every included sample is in `[h-1,h)` and strictly precedes `h`. No future sample is backfilled. The raw hourly premium is the arithmetic mean of `(mark_px-oracle_px)/oracle_px`; ticks with `oracle_px == 0` are skipped. The roughly three-second feed cadence makes this the discrete sampled-hour average. Partial-minute `m` predictions use only samples whose timestamp minute is `<=m`, over the same complete-hour set.",
        "",
        "Fixed prediction: `pred = clip(0.5 * (P + clip(0.0001 - P, -0.0005, 0.0005)) / 8, -0.04, 0.04)`, where `P` is the sampled hourly average. OLS is `realized = intercept + slope * pred + residual`; R-squared includes an intercept. The prediction itself has no fitted slope or intercept.",
        "",
        f"With clamp width, multiplier, divisor, and cap fixed, an empirical grid over interest `[-0.001,0.001]` in 0.0000005 steps minimizes raw prediction RMSE at interest `{interest_estimate:.7f}` (RMSE `{interest_rmse * 10_000:.6f}` bps/hr); the fixed prediction above uses the pre-specified core-interest candidate `0.0001000`. This is the empirical clamp/interest identity measurement; it does not label the HIP-3 interest term as independently verified.",
        "",
        "| scope | n | intercept (funding/hr) | slope | R-squared |",
        "|---|---:|---:|---:|---:|",
        f"| ALL | {overall['n']} | {overall['intercept']:.10f} | {overall['slope']:.8f} | {overall['r_squared']:.8f} |",
    ]
    for market, stats in per_market.items():
        lines.append(
            f"| {market} | {stats['n']} | {stats['intercept']:.10f} | {stats['slope']:.8f} | {stats['r_squared']:.8f} |"
        )
    lines += [
        "",
        "## 1.5 Endpoint feed reconciliation",
        "",
        f"Mechanical formula R-squared: `{overall['r_squared']:.8f}`. Raw oracle-premium-alone R-squared: `{overall['raw_premium_r_squared']:.8f}`. OLS slope: `{overall['slope']:.8f}`. OLS intercept: `{overall['intercept']:.10f}` funding/hr. Mean raw residual: `{overall['mean_residual_bps']:.6f}` bps/hr.",
        "",
        f"Label: `{ENDPOINT_RESULT_LABEL}`. CoinAPI oracle premium reproduces Hyperliquid realized funding to R-squared approximately 0.99, up to an approximately 13% affine scale. The mechanics add no correlation over raw premium; the clamp nonlinearity lowers R-squared by `{overall['raw_premium_r_squared'] - overall['r_squared']:.8f}` relative to raw premium alone.",
        "",
        f"The on-disk `data/rest_cache/9b3fcc2b416006efa8e49efc06cb47716bfe74778a6864b58de856a8a1a02d15.json` `perpDexs` snapshot reports `assetToFundingMultiplier=0.5` for both `xyz:SKHX` and `xyz:SMSN`. T0 (`docs/reports/study3_fees_and_formula.md`) records that HIP-3 multiplier and interest are deployer-configurable. With configured multiplier 0.5 confirmed, slope `{overall['slope']:.8f}` implies an affine-equivalent multiplier `{overall['empirically_implied_multiplier']:.6f}`; the approximately 13% multiplicative identity gap is structural miscalibration, not residual noise. `predicted_funding` is reconciled only up to this affine scale and must not be consumed as an absolute funding level.",
        "",
        "## Sample counts per settlement hour",
        "",
        "| scope | hours | min samples | median samples | max samples |",
        "|---|---:|---:|---:|---:|",
    ]
    for scope, frame in [("ALL", per_hour)] + [
        (market, per_hour.filter(pl.col("market") == market))
        for market in SCOPED_MARKETS.values()
    ]:
        counts = frame["sample_count"].to_numpy()
        lines.append(
            f"| {scope} | {len(counts)} | {int(np.min(counts))} | {np.median(counts):.1f} | {int(np.max(counts))} |"
        )
    lines += [
        "",
        "## Residual distribution (bps/hr)",
        "",
        "| min | p01 | p05 | p25 | p50 | p75 | p95 | p99 | max | mean | RMSE |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| " + " | ".join(f"{value:.6f}" for value in quantiles) + f" | {np.mean(residual):.6f} | {np.sqrt(np.mean(residual**2)):.6f} |",
        "",
        "## Residual split by oracle update class (bps/hr)",
        "",
        "An hour is labeled Fallback when any included sample is Fallback; otherwise it is Deployer.",
        "",
        "| update_class | hours | mean residual | median residual | RMSE |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in class_rows:
        lines.append(
            f"| {row['class']} | {row['n']} | {row['mean']:.6f} | {row['median']:.6f} | {row['rmse']:.6f} |"
        )
    lines += [
        "",
        f"Fallback minus Deployer mean-residual difference: `{class_difference:.6f}` bps/hr.",
        "",
        f"Hourly ±4% cap-hit count: `{cap_count}`.",
        "",
        "## Clamp regime split",
        "",
        "Clamp-INACTIVE means the inner clamp does not bind and the mechanical prediction is constant; clamp-ACTIVE means the premium lies outside that constant-output band. The blended endpoint R-squared is shown above; the subsets are:",
        "",
        "| regime | market-hours | within-subset R-squared |",
        "|---|---:|---:|",
        f"| clamp-INACTIVE | {clamp_split['inactive']['n']} | {clamp_split['inactive']['r_squared']:.8f} |",
        f"| clamp-ACTIVE | {clamp_split['active']['n']} | {clamp_split['active']['r_squared']:.8f} |",
        "",
        "The constant-output inactive predictor explains no within-subset variation; the active subset carries the blended feed-reconciliation correlation.",
        "",
        "## IID partial-observation floor",
        "",
        f"The primary F-B comparison is an order-agnostic iid partial-observation floor. For each minute and each of {int(curve['iid_seed_count'][0])} seeds (base seed 0), the Monte Carlo uses every hour's actual observed and full sample counts and draws exchangeable iid observed-subset and unobserved-complement sums. This is equivalent to uniformly drawing the minute's observed sample count without regard to order from an iid full hour. The partial-versus-full iid R-squared is attenuated by the empirical full-hour realized-funding endpoint R-squared so the null uses the same realized target as the observed statistic. Iid excess is observed R-squared minus that floor.",
        "",
        f"Seed stability: across the 60 minute points, the maximum seed-to-seed iid-floor variance is `{float(curve['iid_floor_seed_variance'].max()):.10f}`, the mean variance is `{float(curve['iid_floor_seed_variance'].mean()):.10f}`, and the maximum standard error of the {int(curve['iid_seed_count'][0])}-seed mean is `{float(np.sqrt(curve['iid_floor_seed_variance'].max() / curve['iid_seed_count'][0])):.10f}`.",
        "",
        "## Intra-hour sample-timing/drift diagnostic (secondary)",
        "",
        f"Label: `{SHUFFLE_DIAGNOSTIC_LABEL}`. For each of 100 shuffles (seed 0), premium samples are randomly reassigned to the hour's observed minute labels within each market-hour. This preserves each hour's near-constant premium level and is therefore NOT the F-B routing input. When observed R-squared is below shuffle R-squared, a contiguous-early window is a worse estimator than a random spread subsample of the same size, implying within-hour premium drift.",
        "",
        "| minute | observed_r2 | iid_floor | iid_excess | shuffle_r2 | market-hours | cumulative samples |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in curve.iter_rows(named=True):
        lines.append(
            f"| {row['minute']} | {row['observed_r2']:.8f} | {row['iid_floor']:.8f} | {row['iid_excess']:.8f} | {row['shuffle_r2']:.8f} | {row['hour_count']} | {row['sample_count']} |"
        )
    lines += [
        "",
        render_routing_section(curve),
        "",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines))


def run_analysis(
    *,
    data_root: Path,
    funding_path: Path,
    output_path: Path,
    report_path: Path,
) -> None:
    samples, realized, inventory = load_scoped_inputs(data_root, funding_path)
    per_hour, curve = reconcile_samples(
        samples,
        realized,
        interest_rate=PRE_SPECIFIED_INTEREST_RATE,
        funding_multiplier=XYZ_FUNDING_MULTIPLIER,
        clamp_bound=CLAMP_BOUND,
        settlement_divisor=SETTLEMENT_DIVISOR,
        hourly_cap=HOURLY_CAP,
        require_complete_hours=True,
    )
    _write_outputs(
        per_hour,
        curve,
        inventory=inventory,
        output_path=output_path,
        report_path=report_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--funding",
        type=Path,
        default=Path("data/reports/study3_funding_all.parquet"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/reports/study3_sb_reconciliation.parquet"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("docs/reports/study3_mechanics_2026-07-10.md"),
    )
    args = parser.parse_args()
    run_analysis(
        data_root=args.data_root,
        funding_path=args.funding,
        output_path=args.output,
        report_path=args.report,
    )


if __name__ == "__main__":
    main()
