"""Forced-flow proxy tagging for Hyperliquid L4 trades.

G2 was absent in the local HLSYSTEMEVENTS feed, so this module implements the
pre-registered proxy: a same-direction 60-second aggressor burst, a
same-direction three-sigma price displacement, and a repeated taker wallet.
All baselines are the 60 complete one-minute buckets strictly before a bucket.

The implementation approximates the pre-registered sliding 60-second window
with fixed UTC calendar-minute buckets. Bursts that straddle a minute boundary
can therefore be split and under-detected; adjacent buckets are merged only
after each bucket qualifies independently. Candidates with a zero trailing
median trade rate or zero trailing return sigma are deliberately not tagged
because a three-times-zero threshold is undefined. Their abstentions are
counted in optional diagnostics and in the event-table build summary so this
thin-market sensitivity remains observable.
"""

from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
from statistics import median, pstdev
from typing import Iterable, MutableMapping, Sequence

import polars as pl

from charybdis.loaders import parse_flat_file_key, scan_trades


EVENT_SCHEMA: dict[str, pl.DataType] = {
    "market": pl.String,
    "start_time": pl.Datetime("ns"),
    "end_time": pl.Datetime("ns"),
    "direction": pl.String,
    "aggressor_size": pl.Float64,
    "wallets": pl.List(pl.String),
    "trigger_source": pl.String,
    "tag_label": pl.String,
    "trade_count": pl.Int64,
    "trailing_median_trade_rate": pl.Float64,
    "price_displacement": pl.Float64,
    "trailing_return_sigma": pl.Float64,
    "rate_multiple": pl.Float64,
    "displacement_multiple": pl.Float64,
}

_TRADE_COLUMNS = (
    "time_exchange",
    "price",
    "base_amount",
    "taker_side",
    "user_taker",
)


def detect_proxy_events(
    trades: pl.DataFrame,
    *,
    diagnostics: MutableMapping[str, int] | None = None,
) -> pl.DataFrame:
    """Detect proxy-tagged forced-flow events in an in-memory trade slice.

    A candidate is a UTC-aligned one-minute bucket. Its directional trade rate
    is compared with the median of the prior 60 directional minute rates,
    including zero-trade minutes. Its adverse price move is measured from the
    prior minute close to the adverse extreme inside the candidate bucket and
    compared with the population sigma of the prior 60 one-minute returns.
    Candidates abstaining because either baseline is zero are counted in the
    optional ``diagnostics`` mapping.
    """

    required = {"market", *_TRADE_COLUMNS}
    missing = sorted(required - set(trades.columns))
    if missing:
        raise ValueError(f"trade columns absent: {missing}")
    if trades.is_empty():
        _reset_suppression_diagnostics(diagnostics)
        return _empty_events()
    directional, closes = _aggregate_trade_frame(trades)
    return _detect_from_aggregates(
        directional,
        closes,
        diagnostics=diagnostics,
    )


def build_proxy_event_table(
    trades_root: str | Path,
    output_path: str | Path,
    *,
    markets: Sequence[str] = ("SKHX", "SMSN"),
) -> dict[str, object]:
    """Column-project L4 files, detect events, and write the parquet table.

    The returned summary includes ``suppressed_candidates`` diagnostics for
    otherwise eligible candidate buckets whose rate or return baseline is zero.
    """

    wanted = set(markets)
    paths: list[tuple[Path, str]] = []
    for path in sorted(Path(trades_root).rglob("*.csv.gz")):
        try:
            key = parse_flat_file_key(path)
        except ValueError:
            continue
        market = key.coin.rsplit(":", 1)[-1]
        if key.dataset == "TRADES" and key.era == "l4" and market in wanted:
            paths.append((path, market))

    directional_parts: list[pl.DataFrame] = []
    close_parts: list[pl.DataFrame] = []
    scanned_files = 0
    skipped_without_wallets = 0
    skipped_corrupt: list[str] = []
    for path, market in paths:
        try:
            trades = (
                scan_trades(path, columns=_TRADE_COLUMNS)
                .with_columns(pl.lit(market).alias("market"))
                .collect(engine="streaming")
            )
        except OSError as error:
            if "corrupt deflate stream" not in str(error):
                raise
            skipped_corrupt.append(str(path))
            continue
        except ValueError as error:
            if "user_taker" not in str(error):
                raise
            skipped_without_wallets += 1
            continue
        scanned_files += 1
        if trades.is_empty():
            continue
        directional, closes = _aggregate_trade_frame(trades)
        directional_parts.append(directional)
        close_parts.append(closes)

    events = _empty_events()
    suppression_diagnostics: dict[str, int] = {}
    _reset_suppression_diagnostics(suppression_diagnostics)
    scan_start: datetime | None = None
    scan_end: datetime | None = None
    if close_parts:
        directional = pl.concat(directional_parts, how="vertical_relaxed")
        closes = pl.concat(close_parts, how="vertical_relaxed")
        events = _detect_from_aggregates(
            directional,
            closes,
            diagnostics=suppression_diagnostics,
        )
        scan_start = closes["minute"].min()
        scan_end = closes["minute"].max()

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    events.write_parquet(destination)
    counts = {
        market: events.filter(pl.col("market") == market).height for market in markets
    }
    return {
        "output": str(destination),
        "events": counts,
        "scanned_files": scanned_files,
        "skipped_without_user_taker": skipped_without_wallets,
        "skipped_corrupt_files": skipped_corrupt,
        "scan_start": scan_start.isoformat() if scan_start else None,
        "scan_end": scan_end.isoformat() if scan_end else None,
        "tag_label": "proxy-tagged",
        "suppressed_candidates": suppression_diagnostics,
    }


def _aggregate_trade_frame(trades: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    frame = (
        trades.select("market", *_TRADE_COLUMNS)
        .filter(
            pl.col("time_exchange").is_not_null()
            & pl.col("price").is_not_null()
            & (pl.col("price") > 0.0)
            & pl.col("base_amount").is_not_null()
            & pl.col("taker_side").is_in(["BUY", "SELL"])
        )
        .sort(["market", "time_exchange"])
        .with_columns(pl.col("time_exchange").dt.truncate("1m").alias("minute"))
    )
    closes = frame.group_by("market", "minute", maintain_order=True).agg(
        pl.col("time_exchange").last().alias("close_time"),
        pl.col("price").last().cast(pl.Float64).alias("close"),
    )
    wallet_counts = frame.group_by(
        "market", "minute", "taker_side", "user_taker"
    ).agg(pl.len().alias("wallet_trade_count"))
    repeated_wallets = (
        wallet_counts.filter(
            pl.col("user_taker").is_not_null()
            & (pl.col("user_taker") != "")
            & (pl.col("wallet_trade_count") >= 2)
        )
        .group_by("market", "minute", "taker_side")
        .agg(pl.col("user_taker").unique().sort().alias("wallets"))
    )
    directional = (
        frame.group_by("market", "minute", "taker_side").agg(
            pl.len().cast(pl.Int64).alias("trade_count"),
            pl.col("base_amount").sum().cast(pl.Float64).alias("aggressor_size"),
            pl.col("time_exchange").min().alias("start_time"),
            pl.col("time_exchange").max().alias("end_time"),
            pl.col("price").min().cast(pl.Float64).alias("min_price"),
            pl.col("price").max().cast(pl.Float64).alias("max_price"),
        )
        .join(
            repeated_wallets,
            on=["market", "minute", "taker_side"],
            how="left",
        )
        .with_columns(
            pl.col("wallets").fill_null(pl.lit([], dtype=pl.List(pl.String)))
        )
    )
    return directional, closes


def _detect_from_aggregates(
    directional: pl.DataFrame,
    closes: pl.DataFrame,
    *,
    diagnostics: MutableMapping[str, int] | None = None,
) -> pl.DataFrame:
    _reset_suppression_diagnostics(diagnostics)
    if closes.is_empty():
        return _empty_events()
    directional, closes = _coalesce_aggregates(directional, closes)
    close_by_market: dict[str, dict[datetime, float]] = {}
    for market, minute, close in closes.select(
        "market", "minute", "close"
    ).iter_rows():
        close_by_market.setdefault(market, {})[minute] = float(close)
    direction_by_market: dict[
        str, dict[tuple[datetime, str], dict[str, object]]
    ] = {}
    for row in directional.iter_rows(named=True):
        key = (row["minute"], row["taker_side"])
        direction_by_market.setdefault(row["market"], {})[key] = row

    candidates: list[dict[str, object]] = []
    for market, close_map in close_by_market.items():
        minute = min(close_map)
        last_minute = max(close_map)
        previous_close: float | None = None
        return_history: deque[float] = deque(maxlen=60)
        rate_history = {
            "BUY": deque(maxlen=60),
            "SELL": deque(maxlen=60),
        }
        rows = direction_by_market.get(market, {})
        while minute <= last_minute:
            close = close_map.get(minute, previous_close)
            current_return = (
                math.log(close / previous_close)
                if close is not None and previous_close is not None
                else 0.0
            )
            for side in ("BUY", "SELL"):
                row = rows.get((minute, side))
                count = int(row["trade_count"]) if row else 0
                if (
                    row is not None
                    and row["wallets"]
                    and previous_close is not None
                    and len(rate_history[side]) == 60
                    and len(return_history) == 60
                ):
                    baseline_rate = float(median(rate_history[side]))
                    sigma = float(pstdev(return_history))
                    adverse = float(
                        row["min_price"] if side == "SELL" else row["max_price"]
                    )
                    signed_move = math.log(adverse / previous_close)
                    directional_move = -signed_move if side == "SELL" else signed_move
                    rate_threshold_met = count >= 3.0 * baseline_rate
                    displacement_threshold_met = directional_move >= 3.0 * sigma
                    if (
                        (baseline_rate == 0.0 or sigma == 0.0)
                        and rate_threshold_met
                        and displacement_threshold_met
                    ):
                        if diagnostics is not None:
                            diagnostics["total"] += 1
                            if baseline_rate == 0.0:
                                diagnostics["zero_baseline_rate"] += 1
                            if sigma == 0.0:
                                diagnostics["zero_return_sigma"] += 1
                    elif rate_threshold_met and displacement_threshold_met:
                        candidates.append(
                            {
                                "market": market,
                                "start_time": row["start_time"],
                                "end_time": row["end_time"],
                                "direction": side,
                                "aggressor_size": float(row["aggressor_size"]),
                                "wallets": sorted(row["wallets"]),
                                "trigger_source": "proxy",
                                "tag_label": "proxy-tagged",
                                "trade_count": count,
                                "trailing_median_trade_rate": baseline_rate,
                                "price_displacement": directional_move,
                                "trailing_return_sigma": sigma,
                                "rate_multiple": count / baseline_rate,
                                "displacement_multiple": directional_move / sigma,
                            }
                        )
                rate_history[side].append(count)
            return_history.append(current_return)
            if close is not None:
                previous_close = close
            minute += timedelta(minutes=1)
    return _events_frame(_merge_adjacent(candidates))


def _coalesce_aggregates(
    directional: pl.DataFrame,
    closes: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Merge aggregate keys that overlap across source-file boundaries."""

    direction_keys = ["market", "minute", "taker_side"]
    combined_directional = directional.group_by(direction_keys).agg(
        pl.col("trade_count").sum().cast(pl.Int64).alias("trade_count"),
        pl.col("aggressor_size").sum().cast(pl.Float64).alias("aggressor_size"),
        pl.col("start_time").min().alias("start_time"),
        pl.col("end_time").max().alias("end_time"),
        pl.col("min_price").min().cast(pl.Float64).alias("min_price"),
        pl.col("max_price").max().cast(pl.Float64).alias("max_price"),
    )
    combined_wallets = (
        directional.select(*direction_keys, "wallets")
        .explode("wallets", empty_as_null=True)
        .filter(pl.col("wallets").is_not_null() & (pl.col("wallets") != ""))
        .group_by(direction_keys)
        .agg(pl.col("wallets").unique().sort().alias("wallets"))
    )
    combined_directional = combined_directional.join(
        combined_wallets,
        on=direction_keys,
        how="left",
    ).with_columns(
        pl.col("wallets").fill_null(pl.lit([], dtype=pl.List(pl.String)))
    )

    close_keys = ["market", "minute"]
    if "close_time" in closes.columns:
        combined_closes = (
            closes.sort([*close_keys, "close_time"])
            .group_by(close_keys, maintain_order=True)
            .agg(
                pl.col("close_time").last().alias("close_time"),
                pl.col("close").last().cast(pl.Float64).alias("close"),
            )
        )
    else:
        combined_closes = closes.group_by(close_keys, maintain_order=True).agg(
            pl.col("close").last().cast(pl.Float64).alias("close")
        )
    return combined_directional, combined_closes


def _reset_suppression_diagnostics(
    diagnostics: MutableMapping[str, int] | None,
) -> None:
    if diagnostics is None:
        return
    diagnostics.clear()
    diagnostics.update(
        {
            "total": 0,
            "zero_baseline_rate": 0,
            "zero_return_sigma": 0,
        }
    )


def _merge_adjacent(events: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    ordered = sorted(events, key=lambda row: (row["market"], row["direction"], row["start_time"]))
    merged: list[dict[str, object]] = []
    for event in ordered:
        if (
            merged
            and merged[-1]["market"] == event["market"]
            and merged[-1]["direction"] == event["direction"]
            and event["start_time"] <= merged[-1]["end_time"] + timedelta(seconds=60)
        ):
            prior = merged[-1]
            prior["end_time"] = max(prior["end_time"], event["end_time"])
            prior["aggressor_size"] += event["aggressor_size"]
            prior["trade_count"] += event["trade_count"]
            prior["wallets"] = sorted(set(prior["wallets"]) | set(event["wallets"]))
            prior["price_displacement"] = max(
                prior["price_displacement"], event["price_displacement"]
            )
            prior["rate_multiple"] = max(prior["rate_multiple"], event["rate_multiple"])
            prior["displacement_multiple"] = max(
                prior["displacement_multiple"], event["displacement_multiple"]
            )
        else:
            merged.append(dict(event))
    return merged


def _events_frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    if not rows:
        return _empty_events()
    return pl.DataFrame(rows, schema=EVENT_SCHEMA).sort(["start_time", "market"])


def _empty_events() -> pl.DataFrame:
    return pl.DataFrame(schema=EVENT_SCHEMA)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trades-root", default="data/T-TRADES")
    parser.add_argument(
        "--output", default="data/reports/forced_flow_events_proxy.parquet"
    )
    args = parser.parse_args()
    print(json.dumps(build_proxy_event_table(args.trades_root, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
