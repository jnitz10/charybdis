"""Study 3 S-D funding-clock analysis primitives and free 1m harvester."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import math
from pathlib import Path
import re
from typing import Protocol, Sequence

import polars as pl

from charybdis.study2 import Window


BRACKET_MINUTES = (-10, -5, -1, 1, 5, 10)
_CANDLE_FILE_RANGE = re.compile(r"_(\d{12})_(\d{12})_1m\.parquet$")


def select_candle_cache_file(paths: Sequence[Path]) -> Path | None:
    """Select the widest cache span, preferring the latest range on ties."""

    candidates: list[tuple[timedelta, datetime, datetime, str, Path]] = []
    for path in paths:
        match = _CANDLE_FILE_RANGE.search(path.name)
        if match is None:
            continue
        start = datetime.strptime(match.group(1), "%Y%m%d%H%M")
        end = datetime.strptime(match.group(2), "%Y%m%d%H%M")
        candidates.append((end - start, end, start, path.name, path))
    return max(candidates)[-1] if candidates else None


def aggregate_l4_trades_to_1m(trades: pl.DataFrame) -> pl.DataFrame:
    """Build trade-time 1m bars without moving observations across boundaries."""

    missing = {"time_exchange", "price"} - set(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    return (
        trades.filter(pl.col("price").is_not_null() & (pl.col("price") > 0))
        .sort("time_exchange")
        .with_columns(pl.col("time_exchange").dt.truncate("1m").alias("minute"))
        .group_by("minute", maintain_order=True)
        .agg(
            pl.col("price").first().alias("open"),
            pl.col("price").last().alias("close"),
            pl.col("time_exchange").first().alias("time_open"),
            pl.col("time_exchange").last().alias("time_close"),
        )
        .select("time_open", "time_close", "open", "close")
    )


class CandleClient(Protocol):
    def candle_snapshot(
        self, market: str, interval: str, start_ms: int, end_ms: int
    ) -> pl.DataFrame: ...


@dataclass(frozen=True)
class HarvestResult:
    estimated_calls: int
    actual_client_calls: int
    cache_hits: int
    output_paths: tuple[Path, ...]


def bracket_side(timestamp: datetime, settlement: datetime) -> str:
    """Classify timestamps around the instant, including equality explicitly."""

    if timestamp < settlement:
        return "pre"
    if timestamp > settlement:
        return "post"
    return "settlement_instant"


def bracket_window(settlement: datetime, bracket_minutes: int) -> Window:
    if bracket_minutes not in BRACKET_MINUTES:
        raise ValueError(f"unsupported bracket: {bracket_minutes}")
    delta = timedelta(minutes=abs(bracket_minutes))
    if bracket_minutes < 0:
        return Window(settlement - delta, settlement)
    return Window(settlement, settlement + delta)


def inside_bracket_return(
    times: Sequence[datetime],
    opens: Sequence[float],
    closes: Sequence[float],
    start: datetime,
    end: datetime,
) -> tuple[float | None, int]:
    """First-open to last-close return for bar closes strictly in ``(start, end)``."""

    from bisect import bisect_left, bisect_right

    left = bisect_right(times, start)
    right = bisect_left(times, end)
    if right - left < 1:
        return None, right - left
    return math.log(closes[right - 1] / opens[left]), right - left


def settlement_control_window(settlement: datetime, bracket_minutes: int) -> Window:
    """Same-direction bracket around the within-hour ``settlement + 30m`` placebo."""

    if bracket_minutes not in BRACKET_MINUTES:
        raise ValueError(f"unsupported bracket: {bracket_minutes}")
    control = settlement + timedelta(minutes=30)
    width = timedelta(minutes=abs(bracket_minutes))
    if bracket_minutes < 0:
        return Window(control - width, control)
    return Window(control, control + width)


def wallet_window_events(trades: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Aggregate repeat-wallet settlement windows and their paired ``t+30m`` placebo."""

    required = {"market", "time_exchange", "user_taker", "signed_notional"}
    missing = required - set(trades.columns)
    if missing:
        raise ValueError(f"trades missing columns: {sorted(missing)}")
    assigned = (
        trades.with_columns(
            pl.col("time_exchange").dt.truncate("1h").alias("hour"),
            pl.col("time_exchange").dt.minute().alias("minute"),
        )
        .filter(
            (pl.col("minute") >= 50)
            | (pl.col("minute") < 10)
            | pl.col("minute").is_between(20, 39)
        )
        .with_columns(
            pl.when((pl.col("minute") >= 50) | (pl.col("minute") < 10))
            .then(pl.lit("settlement"))
            .otherwise(pl.lit("baseline"))
            .alias("window_kind"),
            pl.when(pl.col("minute") >= 50)
            .then(pl.col("hour") + pl.duration(hours=1))
            .otherwise(pl.col("hour"))
            .alias("settlement_time"),
            pl.when((pl.col("minute") >= 50) | pl.col("minute").is_between(20, 29))
            .then(pl.lit("pre"))
            .otherwise(pl.lit("post"))
            .alias("phase"),
        )
    )
    wallet = (
        assigned.group_by(
            "market", "settlement_time", "user_taker", "window_kind", "phase"
        )
        .agg(pl.len().alias("trade_count"), pl.col("signed_notional").sum())
        .pivot(
            on="phase",
            index=["market", "settlement_time", "user_taker", "window_kind"],
            values=["trade_count", "signed_notional"],
        )
        .fill_null(0)
        .filter((pl.col("trade_count_pre") + pl.col("trade_count_post")) >= 2)
        .with_columns(
            ((pl.col("signed_notional_pre") < 0) & (pl.col("signed_notional_post") > 0))
            .alias("short_open_then_close")
        )
    )
    by_window = wallet.group_by("market", "settlement_time", "window_kind").agg(
        pl.col("signed_notional_pre").sum().alias("pre_signed_notional"),
        pl.col("signed_notional_post").sum().alias("post_signed_notional"),
        pl.len().alias("repeat_wallets"),
        pl.col("short_open_then_close").mean().alias("short_open_close_share"),
    )
    settlement = by_window.filter(pl.col("window_kind") == "settlement").drop("window_kind")
    baseline = by_window.filter(pl.col("window_kind") == "baseline").select(
        "market",
        "settlement_time",
        pl.col("short_open_close_share").alias("baseline_short_open_close_share"),
    )
    events = settlement.join(baseline, on=["market", "settlement_time"], how="left").with_columns(
        (pl.col("short_open_close_share") - pl.col("baseline_short_open_close_share"))
        .alias("short_open_close_share_difference")
    )
    return events, wallet


def estimate_harvest_calls(
    markets: Sequence[str], start: datetime, end: datetime, *, page_size: int = 5_000
) -> int:
    if end <= start:
        raise ValueError("end must be after start")
    minutes = math.ceil((end - start).total_seconds() / 60)
    return len(set(markets)) * math.ceil(minutes / page_size)


def _market_cache_path(output_dir: Path, market: str, start: datetime, end: datetime) -> Path:
    safe = market.replace(":", "__")
    return output_dir / f"{safe}_{start:%Y%m%d%H%M}_{end:%Y%m%d%H%M}_1m.parquet"


def harvest_1m_candles(
    *,
    client: CandleClient,
    markets: Sequence[str],
    start: datetime,
    end: datetime,
    output_dir: str | Path,
) -> HarvestResult:
    """Harvest one file per market; completed files bypass even client cache lookup."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    actual = 0
    hits = 0
    network_before = getattr(client, "rest_calls", None)
    start_utc = start if start.tzinfo is not None else start.replace(tzinfo=UTC)
    end_utc = end if end.tzinfo is not None else end.replace(tzinfo=UTC)
    start_ms = int(start_utc.timestamp() * 1_000)
    end_ms = int(end_utc.timestamp() * 1_000)
    for market in sorted(set(markets)):
        path = _market_cache_path(output, market, start, end)
        paths.append(path)
        if path.exists():
            pl.scan_parquet(path).select(pl.len()).collect()
            hits += 1
            continue
        frame = client.candle_snapshot(market, "1m", start_ms, end_ms)
        actual += 1
        frame.write_parquet(path)
    if network_before is not None:
        actual = int(getattr(client, "rest_calls")) - int(network_before)
    return HarvestResult(
        estimated_calls=estimate_harvest_calls(markets, start, end),
        actual_client_calls=actual,
        cache_hits=hits,
        output_paths=tuple(paths),
    )
