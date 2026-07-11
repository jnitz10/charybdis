"""Causal passive-fill simulation and cluster-bootstrap markout summaries.

The simulator deliberately makes the conservative timing choice that a trade at
the exact timestamp of an L1 change cannot fill the quote joined at that change.
It joins each side independently when that side's touch price or displayed size
changes.  The displayed touch size is queue-ahead: when ``l1`` was reconstructed
from L2 events this is the L2 size at join, otherwise it is the quoted L1 size.

The fill rule still has an unavoidable upper-bound bias: prints do not reveal
cancelled queue ahead, hidden liquidity, order priority, or whether our order
would itself alter subsequent flow.  A qualifying print therefore establishes
only an optimistic upper bound on fills even with the conservative queue test.

Markouts use the latest fully two-sided microprice observed at or before each
horizon; they never require a later row to prove file coverage.  Entry and
horizon observations older than ``max_quote_age_s`` are flagged and represented
as null markouts.  The 60-second default is a tunable modeling choice, not an
estimated parameter.  Naive input timestamps are UTC.  ``hour_of_day`` and
six-hour cluster blocks are also UTC.  ``sweep`` means the single filling print
exceeded queue-ahead; all other filling prints are bucketed as ``trickle``.

Funding uses the latest per-market hourly rate known at fill and holds it fixed
over the short horizon.  Positive funding costs a long (buy fill) and benefits a
short (sell fill).  Holidays are grouped with off-hours weekdays so Study 1 has
exactly the pre-registered RTH/off-hours-weekday/weekend segments.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import math
from pathlib import Path
import random
from typing import Callable, Iterable, Mapping, Sequence

import polars as pl

from charybdis.calendars import label_nyse


HORIZONS_SECONDS: dict[str, int] = {
    "1s": 1,
    "5s": 5,
    "30s": 30,
    "2m": 120,
    "10m": 600,
}

# Hyperliquid base perpetual maker fee assumed by the approved task brief.
# deployerFeeScale is 1.0 for xyz/km/flx/cash, so the engine takes this once as
# bps and permits an explicit override when the official tier is supplied.
DEFAULT_MAKER_FEE_BPS = 1.5
DEFAULT_MAKER_FEE_ASSUMED = True

_L1_COLUMNS = {
    "time_exchange",
    "best_bid_px",
    "best_bid_sx",
    "best_ask_px",
    "best_ask_sx",
}
_TRADE_COLUMNS = {"time_exchange", "price", "base_amount"}


@dataclass(frozen=True)
class BootstrapCI:
    """A pooled point estimate and nonparametric cluster-bootstrap interval."""

    point_estimate: float
    ci_low: float | None
    ci_high: float | None
    n: int
    G: int
    low_cluster: bool


def cluster_bootstrap_statistic(
    frame: pl.DataFrame,
    *,
    statistic: Callable[[pl.DataFrame], float],
    cluster_col: str = "cluster_key",
    n_resamples: int = 2_000,
    seed: int = 0,
    min_clusters: int = 5,
) -> BootstrapCI:
    """Cluster-bootstrap an arbitrary statistic using the Study-1 resampler.

    Repeated sampled clusters repeat all their rows. A private draw-instance
    column lets statistics distinguish duplicate cluster occurrences when
    grouping observations after resampling.
    """

    if n_resamples < 2_000:
        raise ValueError("n_resamples must be at least 2000")
    if not isinstance(min_clusters, int) or isinstance(min_clusters, bool) or min_clusters < 2:
        raise ValueError("min_clusters must be an integer of at least 2")
    _require_columns(frame, {cluster_col}, "bootstrap frame")
    clean = frame.filter(pl.col(cluster_col).is_not_null())
    group_indices = (
        clean.with_row_index("_bootstrap_row")
        .group_by(cluster_col, maintain_order=True)
        .agg(pl.col("_bootstrap_row"))["_bootstrap_row"]
        .to_list()
    )
    if not group_indices:
        raise ValueError("no clustered observations")
    point = float(statistic(clean))
    G = len(group_indices)
    if G < min_clusters:
        return BootstrapCI(point, None, None, clean.height, G, True)
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(n_resamples):
        indices = [
            row
            for _ in range(G)
            for row in group_indices[rng.randrange(G)]
        ]
        value = float(statistic(clean[indices]))
        if math.isfinite(value):
            draws.append(value)
    if not draws:
        raise ValueError("bootstrap statistic produced no finite draws")
    draws.sort()
    return BootstrapCI(
        point_estimate=point,
        ci_low=_percentile(draws, 0.025),
        ci_high=_percentile(draws, 0.975),
        n=clean.height,
        G=G,
        low_cluster=False,
    )


def cluster_bootstrap_panel_statistic(
    frame: pl.DataFrame,
    *,
    statistic: Callable[[pl.DataFrame], float],
    strata_cols: Sequence[str],
    destination_cols: Sequence[str],
    cluster_col: str = "cluster_key",
    n_resamples: int = 2_000,
    seed: int = 0,
    min_clusters: int = 5,
) -> BootstrapCI:
    """Stratified scalar-panel bootstrap preserving destination time slots.

    Each input row is one already-netted portfolio time block. Whole source
    blocks are sampled within each stratum and copied into destination slots;
    destination time columns are restored so repeated blocks remain distinct.
    """

    if n_resamples < 2_000:
        raise ValueError("n_resamples must be at least 2000")
    required = {cluster_col, *strata_cols, *destination_cols}
    _require_columns(frame, required, "panel bootstrap frame")
    clean = frame.filter(pl.col(cluster_col).is_not_null()).with_row_index("_bootstrap_row")
    G = clean[cluster_col].n_unique()
    if G != clean.height:
        raise ValueError("panel bootstrap requires one netted row per time-block cluster")
    point = float(statistic(clean.drop("_bootstrap_row")))
    if G < min_clusters:
        return BootstrapCI(point, None, None, clean.height, G, True)
    strata: dict[tuple[object, ...], list[int]] = {}
    for index in range(clean.height):
        signature = tuple(clean[column][index] for column in strata_cols)
        strata.setdefault(signature, []).append(index)
    rng = random.Random(seed)
    draws: list[float] = []
    destinations = clean.select(list(destination_cols))
    payload = clean.drop("_bootstrap_row")
    for _ in range(n_resamples):
        source_indices = list(range(clean.height))
        for compatible_blocks in strata.values():
            for destination_index in compatible_blocks:
                source_indices[destination_index] = compatible_blocks[rng.randrange(len(compatible_blocks))]
        sampled = payload[source_indices].with_columns(
            *[destinations[column].alias(column) for column in destination_cols]
        )
        value = float(statistic(sampled))
        if math.isfinite(value):
            draws.append(value)
    if not draws:
        raise ValueError("panel bootstrap statistic produced no finite draws")
    draws.sort()
    return BootstrapCI(
        point_estimate=point, ci_low=_percentile(draws, 0.025),
        ci_high=_percentile(draws, 0.975), n=clean.height, G=G, low_cluster=False,
    )


@dataclass
class _JoinedQuote:
    side: str
    price: float
    queue_ahead: float
    join_time: datetime
    at_price_cumulative: float = 0.0


def microprice_frame(l1: pl.DataFrame) -> pl.DataFrame:
    """Return microprices for fully two-sided L1 rows, skipping one-sided rows.

    ``microprice = (bid_px * ask_sz + ask_px * bid_sz) / (ask_sz + bid_sz)``.
    Rows with a missing side or non-positive price/size are absent, never filled
    with zero.
    """

    _require_columns(l1, _L1_COLUMNS, "l1")
    _require_monotonic(l1, "l1")
    valid = l1.filter(
        pl.all_horizontal(
            pl.col("best_bid_px").is_not_null(),
            pl.col("best_bid_sx").is_not_null(),
            pl.col("best_ask_px").is_not_null(),
            pl.col("best_ask_sx").is_not_null(),
            pl.col("best_bid_px") > 0,
            pl.col("best_bid_sx") > 0,
            pl.col("best_ask_px") > 0,
            pl.col("best_ask_sx") > 0,
        )
    )
    crossed = valid.filter(pl.col("best_bid_px") > pl.col("best_ask_px"))
    if crossed.height:
        raise ValueError("crossed L1 row: best_bid_px exceeds best_ask_px")
    return valid.select(
        pl.col("time_exchange").cast(pl.Datetime("ns")),
        (
            (
                pl.col("best_bid_px") * pl.col("best_ask_sx")
                + pl.col("best_ask_px") * pl.col("best_bid_sx")
            )
            / (pl.col("best_ask_sx") + pl.col("best_bid_sx"))
        ).alias("microprice"),
    )


def build_fill_markouts(
    l1: pl.DataFrame,
    trades: pl.DataFrame,
    *,
    market: str,
    funding: pl.DataFrame,
    maker_fee_bps: float = DEFAULT_MAKER_FEE_BPS,
    max_quote_age_s: float = 60.0,
    horizons: Mapping[str, int] = HORIZONS_SECONDS,
) -> pl.DataFrame:
    """Simulate passive touch fills and calculate causal net markouts.

    Funding must have ``time_exchange``, ``market``, and ``hourly_rate`` (or
    ``funding_rate``).  At least one rate for ``market`` must be known no later
    than every fill; missing history raises instead of silently assuming zero.
    Pass an explicit zero-rate series when zero funding is intended.
    """

    if not market:
        raise ValueError("market must be non-empty")
    if not math.isfinite(maker_fee_bps) or maker_fee_bps < 0:
        raise ValueError("maker_fee_bps must be finite and non-negative")
    if not math.isfinite(max_quote_age_s) or max_quote_age_s < 0:
        raise ValueError("max_quote_age_s must be finite and non-negative")
    _validate_horizons(horizons)
    _require_columns(l1, _L1_COLUMNS, "l1")
    _require_columns(trades, _TRADE_COLUMNS, "trades")
    _require_monotonic(l1, "l1")
    _require_monotonic(trades, "trades")

    microprices = microprice_frame(l1)
    micro_times = microprices["time_exchange"].to_list()
    micro_values = microprices["microprice"].to_list()
    rates = _funding_rates(funding, market)

    l1_by_time = {row["time_exchange"]: row for row in l1.iter_rows(named=True)}
    if len(l1_by_time) != l1.height:
        raise ValueError("l1 contains duplicate time_exchange rows")
    trades_by_time: dict[datetime, list[dict[str, object]]] = {}
    for row in trades.iter_rows(named=True):
        trades_by_time.setdefault(row["time_exchange"], []).append(row)

    active: dict[str, _JoinedQuote | None] = {"buy": None, "sell": None}
    prior_touch: dict[str, tuple[float, float] | None] = {
        "buy": None,
        "sell": None,
    }
    fills: list[dict[str, object]] = []
    for timestamp in sorted(set(l1_by_time) | set(trades_by_time)):
        book_row = l1_by_time.get(timestamp)
        if book_row is not None:
            # Same-time trades are discarded because event ordering is unknown;
            # they cannot be credited to either the old or newly joined quote.
            _apply_l1_change(book_row, timestamp, active, prior_touch)
            continue
        for trade in trades_by_time.get(timestamp, []):
            _apply_trade(trade, timestamp, active, fills, market)

    records: list[dict[str, object]] = []
    for fill in fills:
        fill_time = fill["fill_time"]
        assert isinstance(fill_time, datetime)
        hourly_rate = _rate_asof(rates, fill_time)
        side_sign = 1.0 if fill["side"] == "buy" else -1.0
        fill_price = float(fill["fill_price"])
        entry_observation = _microprice_asof(micro_times, micro_values, fill_time)
        entry_stale = _quote_is_stale(
            entry_observation,
            fill_time,
            max_quote_age_s,
        )
        record = dict(fill)
        record.update(
            {
                "segment": _study_segment(fill_time),
                "hour_of_day": _as_utc_naive(fill_time).hour,
                "cluster_key": _cluster_key(market, fill_time),
                "maker_fee_bps": float(maker_fee_bps),
                "funding_hourly_rate": hourly_rate,
            }
        )
        for label, seconds in horizons.items():
            # Direct arithmetic preserves the handoff contract that naive input
            # datetimes are UTC; datetime.timestamp() would apply the host TZ.
            target_time = _as_utc_naive(fill_time) + timedelta(seconds=seconds)
            observed = _microprice_asof(
                micro_times,
                micro_values,
                target_time,
            )
            stale = entry_stale or _quote_is_stale(
                observed,
                target_time,
                max_quote_age_s,
            )
            observed_value = None if stale else observed[1]
            gross = (
                None
                if observed_value is None
                else side_sign
                * (observed_value - fill_price)
                / fill_price
                * 10_000.0
            )
            funding_bps = side_sign * hourly_rate * (seconds / 3600.0) * 10_000.0
            record[f"microprice_{label}"] = observed_value
            record[f"gross_markout_{label}_bps"] = gross
            record[f"funding_drift_{label}_bps"] = funding_bps
            record[f"net_markout_{label}_bps"] = (
                None if gross is None else gross - maker_fee_bps - funding_bps
            )
            record[f"stale_{label}"] = stale
        records.append(record)
    return _records_frame(records, horizons)


def cluster_bootstrap_ci(
    frame: pl.DataFrame,
    *,
    value_col: str,
    cluster_col: str = "cluster_key",
    n_resamples: int = 2_000,
    seed: int = 0,
    min_clusters: int = 5,
) -> BootstrapCI:
    """Percentile CI from resampling whole clusters with replacement.

    The statistic in every draw is the pooled arithmetic mean of all rows in
    the sampled clusters.  Repeated clusters repeat all their rows, preserving
    unequal cluster sizes.  ``n_resamples`` is intentionally constrained to the
    pre-registered minimum of 2,000.  Below ``min_clusters`` the point estimate
    and G are retained, but the interval is undefined and ``low_cluster`` is
    true.  In particular, G=1 can never produce a zero-width numeric interval.
    The pre-registered "CIs separating" falsification must treat an undefined
    interval as insufficient evidence, never as separation.
    """

    if n_resamples < 2_000:
        raise ValueError("n_resamples must be at least 2000")
    if not isinstance(min_clusters, int) or isinstance(min_clusters, bool) or min_clusters < 2:
        raise ValueError("min_clusters must be an integer of at least 2")
    _require_columns(frame, {value_col, cluster_col}, "bootstrap frame")
    clusters: dict[object, list[float]] = {}
    for cluster, value in frame.select(cluster_col, value_col).iter_rows():
        if cluster is None or value is None:
            continue
        numeric = float(value)
        if not math.isfinite(numeric):
            continue
        clusters.setdefault(cluster, []).append(numeric)
    if not clusters:
        raise ValueError("no finite clustered observations")

    payloads = list(clusters.values())
    totals = [sum(payload) for payload in payloads]
    counts = [len(payload) for payload in payloads]
    all_total = sum(totals)
    n = sum(counts)
    G = len(payloads)
    point_estimate = all_total / n
    if G < min_clusters:
        return BootstrapCI(
            point_estimate=point_estimate,
            ci_low=None,
            ci_high=None,
            n=n,
            G=G,
            low_cluster=True,
        )
    rng = random.Random(seed)
    draws: list[float] = []
    for _ in range(n_resamples):
        draw_total = 0.0
        draw_count = 0
        for _ in range(G):
            index = rng.randrange(G)
            draw_total += totals[index]
            draw_count += counts[index]
        draws.append(draw_total / draw_count)
    draws.sort()
    return BootstrapCI(
        point_estimate=point_estimate,
        ci_low=_percentile(draws, 0.025),
        ci_high=_percentile(draws, 0.975),
        n=n,
        G=G,
        low_cluster=False,
    )


def primary_summary(
    fills: pl.DataFrame,
    *,
    n_resamples: int = 2_000,
    seed: int = 0,
    min_clusters: int = 5,
) -> pl.DataFrame:
    """Build the pre-registered 30-second, both-sides-pooled summary.

    Null-CI/low-cluster cells are insufficient evidence and must never be
    interpreted as CI separation in the pre-registered falsification.
    """

    return _summary(
        fills,
        by=["market", "segment"],
        horizon="30s",
        n_resamples=n_resamples,
        seed=seed,
        min_clusters=min_clusters,
    )


def secondary_summary(
    fills: pl.DataFrame,
    *,
    by: Sequence[str],
    horizon: str = "30s",
    n_resamples: int = 2_000,
    seed: int = 0,
    min_clusters: int = 5,
) -> pl.DataFrame:
    """Build a cluster-bootstrap summary for side/hour/size-bucket hooks."""

    allowed = {"market", "segment", "side", "hour_of_day", "size_bucket"}
    if not by or any(column not in allowed for column in by):
        raise ValueError(f"by must use one or more of {sorted(allowed)}")
    return _summary(
        fills,
        by=list(by),
        horizon=horizon,
        n_resamples=n_resamples,
        seed=seed,
        min_clusters=min_clusters,
    )


def write_fill_records(fills: pl.DataFrame, path: str | Path) -> None:
    """Write the sole per-fill artifact as parquet."""

    fills.write_parquet(path)


def _apply_l1_change(
    row: Mapping[str, object],
    timestamp: datetime,
    active: dict[str, _JoinedQuote | None],
    prior_touch: dict[str, tuple[float, float] | None],
) -> None:
    fields = ("best_bid_px", "best_bid_sx", "best_ask_px", "best_ask_sx")
    if any(row[field] is None for field in fields):
        active["buy"] = active["sell"] = None
        prior_touch["buy"] = prior_touch["sell"] = None
        return
    values = [float(row[field]) for field in fields]
    bid_px, bid_size, ask_px, ask_size = values
    if any(not math.isfinite(value) or value <= 0 for value in values):
        active["buy"] = active["sell"] = None
        prior_touch["buy"] = prior_touch["sell"] = None
        return
    if bid_px > ask_px:
        raise ValueError(f"crossed L1 row at {timestamp!r}")
    for side, price, size in (
        ("buy", bid_px, bid_size),
        ("sell", ask_px, ask_size),
    ):
        touch = (price, size)
        if touch != prior_touch[side]:
            active[side] = _JoinedQuote(side, price, size, timestamp)
            prior_touch[side] = touch


def _apply_trade(
    trade: Mapping[str, object],
    timestamp: datetime,
    active: dict[str, _JoinedQuote | None],
    fills: list[dict[str, object]],
    market: str,
) -> None:
    if trade["price"] is None or trade["base_amount"] is None:
        return
    price = float(trade["price"])
    amount = float(trade["base_amount"])
    if not math.isfinite(price) or not math.isfinite(amount) or price <= 0 or amount <= 0:
        raise ValueError(f"invalid trade price/size at {timestamp!r}")
    for side in ("buy", "sell"):
        quote = active[side]
        if quote is None or timestamp <= quote.join_time:
            continue
        through = price < quote.price if side == "buy" else price > quote.price
        if price == quote.price:
            quote.at_price_cumulative += amount
        at_price_fill = price == quote.price and quote.at_price_cumulative > quote.queue_ahead
        if through or at_price_fill:
            fills.append(
                {
                    "market": market,
                    "fill_time": timestamp,
                    "join_time": quote.join_time,
                    "side": side,
                    "fill_price": quote.price,
                    "filling_print_price": price,
                    "filling_print_size": amount,
                    "queue_ahead": quote.queue_ahead,
                    "at_price_cumulative": quote.at_price_cumulative,
                    "size_bucket": "sweep" if amount > quote.queue_ahead else "trickle",
                }
            )
            active[side] = None


def _funding_rates(funding: pl.DataFrame, market: str) -> list[tuple[datetime, float]]:
    rate_col = "hourly_rate" if "hourly_rate" in funding.columns else "funding_rate"
    _require_columns(funding, {"time_exchange", "market", rate_col}, "funding")
    selected = funding.filter(pl.col("market") == market).select(
        "time_exchange", rate_col
    )
    _require_monotonic(selected, "funding")
    rates: list[tuple[datetime, float]] = []
    for timestamp, rate in selected.iter_rows():
        if rate is None:
            continue
        numeric = float(rate)
        if not math.isfinite(numeric):
            raise ValueError(f"non-finite funding rate at {timestamp!r}")
        rates.append((timestamp, numeric))
    if not rates:
        raise ValueError(f"no funding rates for market {market!r}")
    return rates


def _rate_asof(rates: list[tuple[datetime, float]], timestamp: datetime) -> float:
    times = [item[0] for item in rates]
    index = bisect_right(times, timestamp) - 1
    if index < 0:
        raise ValueError(f"no funding rate known by fill time {timestamp!r}")
    return rates[index][1]


def _microprice_asof(
    times: list[datetime],
    values: list[float],
    target: datetime,
) -> tuple[datetime, float] | None:
    index = bisect_right(times, target) - 1
    return None if index < 0 else (times[index], float(values[index]))


def _quote_is_stale(
    observation: tuple[datetime, float] | None,
    target: datetime,
    max_quote_age_s: float,
) -> bool:
    return observation is None or observation[0] < target - timedelta(
        seconds=max_quote_age_s
    )


def _study_segment(timestamp: datetime) -> str:
    label = label_nyse(_as_utc_naive(timestamp).replace(tzinfo=UTC))
    return "off-hours-weekday" if label == "holiday" else label


def _cluster_key(market: str, timestamp: datetime) -> str:
    utc = _as_utc_naive(timestamp)
    block = utc.replace(hour=(utc.hour // 6) * 6, minute=0, second=0, microsecond=0)
    return f"{market}|{block.isoformat()}"


def _as_utc_naive(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        return timestamp
    return timestamp.astimezone(UTC).replace(tzinfo=None)


def _summary(
    fills: pl.DataFrame,
    *,
    by: list[str],
    horizon: str,
    n_resamples: int,
    seed: int,
    min_clusters: int,
) -> pl.DataFrame:
    value_col = f"net_markout_{horizon}_bps"
    _require_columns(
        fills,
        set(by) | {value_col, "cluster_key", "stale_30s"},
        "fills",
    )
    rows: list[dict[str, object]] = []
    if fills.is_empty():
        return pl.DataFrame(
            schema={
                **{column: fills.schema[column] for column in by},
                "horizon": pl.String,
                "point_estimate_bps": pl.Float64,
                "ci_low_bps": pl.Float64,
                "ci_high_bps": pl.Float64,
                "n": pl.Int64,
                "G": pl.Int64,
                "low_cluster": pl.Boolean,
                "staleness_rate_30s": pl.Float64,
            }
        )
    for group in fills.partition_by(by, maintain_order=True):
        first = group.row(0, named=True)
        clean = group.filter(pl.col(value_col).is_not_null())
        ci = (
            None
            if clean.is_empty()
            else cluster_bootstrap_ci(
                clean,
                value_col=value_col,
                n_resamples=n_resamples,
                seed=seed,
                min_clusters=min_clusters,
            )
        )
        rows.append(
            {
                **{column: first[column] for column in by},
                "horizon": horizon,
                "point_estimate_bps": None if ci is None else ci.point_estimate,
                "ci_low_bps": None if ci is None else ci.ci_low,
                "ci_high_bps": None if ci is None else ci.ci_high,
                "n": 0 if ci is None else ci.n,
                "G": 0 if ci is None else ci.G,
                "low_cluster": True if ci is None else ci.low_cluster,
                "staleness_rate_30s": group["stale_30s"].sum() / group.height,
            }
        )
    return pl.DataFrame(rows).select(
        *by,
        "horizon",
        "point_estimate_bps",
        "ci_low_bps",
        "ci_high_bps",
        "n",
        "G",
        "low_cluster",
        "staleness_rate_30s",
    )


def _records_frame(
    records: list[dict[str, object]], horizons: Mapping[str, int]
) -> pl.DataFrame:
    schema: dict[str, pl.DataType] = {
        "market": pl.String,
        "fill_time": pl.Datetime("ns"),
        "join_time": pl.Datetime("ns"),
        "side": pl.String,
        "fill_price": pl.Float64,
        "filling_print_price": pl.Float64,
        "filling_print_size": pl.Float64,
        "queue_ahead": pl.Float64,
        "at_price_cumulative": pl.Float64,
        "size_bucket": pl.String,
        "segment": pl.String,
        "hour_of_day": pl.Int64,
        "cluster_key": pl.String,
        "maker_fee_bps": pl.Float64,
        "funding_hourly_rate": pl.Float64,
    }
    for label in horizons:
        schema[f"microprice_{label}"] = pl.Float64
        schema[f"gross_markout_{label}_bps"] = pl.Float64
        schema[f"funding_drift_{label}_bps"] = pl.Float64
        schema[f"net_markout_{label}_bps"] = pl.Float64
        schema[f"stale_{label}"] = pl.Boolean
    if not records:
        return pl.DataFrame(schema=schema)
    return pl.DataFrame(records, schema=schema)


def _require_columns(frame: pl.DataFrame, required: Iterable[str], name: str) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _require_monotonic(frame: pl.DataFrame, name: str) -> None:
    if "time_exchange" not in frame.columns or frame.height < 2:
        return
    times = frame["time_exchange"].to_list()
    if any(current < previous for previous, current in zip(times, times[1:])):
        raise ValueError(f"{name} time_exchange must be monotonic")


def _validate_horizons(horizons: Mapping[str, int]) -> None:
    if not horizons:
        raise ValueError("horizons must be non-empty")
    if any(not label or not isinstance(seconds, int) or seconds <= 0 for label, seconds in horizons.items()):
        raise ValueError("horizon labels must be non-empty and seconds positive integers")


def _percentile(sorted_values: list[float], probability: float) -> float:
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight
