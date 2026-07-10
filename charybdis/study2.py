"""Pure planning and anatomy primitives for Study 2.

All timestamps are exchange timestamps represented as naive UTC datetimes, as
they are in the CoinAPI parquet/CSV loaders.  The module contains no downloader
or credential handling; paid I/O is orchestrated separately by
``charybdis.run_study2`` after the dry-run gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from typing import Callable, Iterable, Sequence

import polars as pl

from charybdis.markout import microprice_frame


PROXY_LABEL = "proxy-tagged"
PULL_BUDGET_USD = 40.0


@dataclass(frozen=True, order=True)
class Window:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("window end precedes start")

    @property
    def duration(self) -> timedelta:
        return self.end - self.start


@dataclass(frozen=True)
class PullWindowPair:
    pair_id: str
    market: str
    event: Window
    baseline: Window | None
    burst_strength: float
    object_keys: tuple[str, ...]
    event_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class BudgetSelection:
    selected_pairs: tuple[PullWindowPair, ...]
    dropped_pairs: tuple[PullWindowPair, ...]
    original_cost_usd: float
    selected_cost_usd: float
    downscoped: bool
    coverage_cut_reason: str | None


@dataclass(frozen=True)
class MergedEventWindow:
    pair_id: str
    market: str
    window: Window
    event_ids: tuple[str, ...]
    burst_strength: float


def merge_event_windows(
    events: pl.DataFrame,
    *,
    padding: timedelta = timedelta(minutes=30),
) -> tuple[MergedEventWindow, ...]:
    """Expand tagged events and merge overlapping or exactly adjacent spans."""

    required = {
        "market",
        "start_time",
        "end_time",
        "rate_multiple",
        "displacement_multiple",
        "tag_label",
    }
    missing = sorted(required - set(events.columns))
    if missing:
        raise ValueError(f"events missing required columns: {missing}")
    if padding < timedelta(0):
        raise ValueError("padding cannot be negative")
    if events.filter(pl.col("tag_label") != PROXY_LABEL).height:
        raise ValueError("window planner accepts only proxy-tagged events")
    merged: list[dict[str, object]] = []
    counters: dict[str, int] = {}
    ordered = events.sort(["market", "start_time", "end_time"])
    for ordinal, event in enumerate(ordered.iter_rows(named=True), start=1):
        market = str(event["market"])
        event_id = f"{market}-{ordinal:06d}"
        start = event["start_time"] - padding
        end = event["end_time"] + padding
        strength = float(event["rate_multiple"]) * float(
            event["displacement_multiple"]
        )
        if (
            merged
            and merged[-1]["market"] == market
            and start <= merged[-1]["end"]
        ):
            merged[-1]["end"] = max(merged[-1]["end"], end)
            merged[-1]["event_ids"].append(event_id)
            merged[-1]["burst_strength"] = max(
                float(merged[-1]["burst_strength"]), strength
            )
            continue
        counters[market] = counters.get(market, 0) + 1
        merged.append(
            {
                "pair_id": f"{market}-W{counters[market]:04d}",
                "market": market,
                "start": start,
                "end": end,
                "event_ids": [event_id],
                "burst_strength": strength,
            }
        )
    return tuple(
        MergedEventWindow(
            pair_id=str(item["pair_id"]),
            market=str(item["market"]),
            window=Window(item["start"], item["end"]),
            event_ids=tuple(item["event_ids"]),
            burst_strength=float(item["burst_strength"]),
        )
        for item in merged
    )


def match_baseline_windows(
    event_windows: Sequence[MergedEventWindow],
    all_events: pl.DataFrame,
    *,
    coverage: dict[str, Window],
) -> tuple[tuple[PullWindowPair, ...], tuple[MergedEventWindow, ...]]:
    """Match same-clock baselines without event contamination or reuse.

    Candidates retain the event window's exact UTC start time-of-day and
    duration.  Search order is nearest calendar day, preferring the earlier day
    on ties.  A candidate and its ±30-minute guard may not intersect any raw
    tagged event, any event pull window, or a baseline already assigned.  Thus
    baseline observations are never duplicated across matched pairs.
    """

    required = {"market", "start_time", "end_time"}
    missing = sorted(required - set(all_events.columns))
    if missing:
        raise ValueError(f"events missing required columns: {missing}")
    event_spans: dict[str, list[Window]] = {}
    for item in event_windows:
        event_spans.setdefault(item.market, []).append(item.window)
    used: dict[str, list[Window]] = {}
    pairs: list[PullWindowPair] = []
    unmatched: list[MergedEventWindow] = []
    for item in sorted(event_windows, key=lambda row: (row.market, row.window.start)):
        bounds = coverage.get(item.market)
        if bounds is None:
            unmatched.append(item)
            continue
        maximum_days = max(1, (bounds.end.date() - bounds.start.date()).days + 1)
        chosen: Window | None = None
        for distance in range(1, maximum_days + 1):
            for signed_days in (-distance, distance):
                start = item.window.start + timedelta(days=signed_days)
                candidate = Window(start, start + item.window.duration)
                if candidate.start < bounds.start or candidate.end > bounds.end:
                    continue
                blocked = [
                    *event_spans.get(item.market, []),
                    *used.get(item.market, []),
                ]
                if any(_windows_overlap(candidate, existing) for existing in blocked):
                    continue
                chosen = candidate
                break
            if chosen is not None:
                break
        if chosen is None:
            unmatched.append(item)
            continue
        used.setdefault(item.market, []).append(chosen)
        pairs.append(
            PullWindowPair(
                pair_id=item.pair_id,
                market=item.market,
                event=item.window,
                baseline=chosen,
                burst_strength=item.burst_strength,
                object_keys=(),
                event_ids=item.event_ids,
            )
        )
    return tuple(pairs), tuple(unmatched)


def hours_touched(window: Window) -> tuple[datetime, ...]:
    """Return UTC hour partitions intersecting a closed pull window."""

    hour = window.start.replace(minute=0, second=0, microsecond=0)
    hours: list[datetime] = []
    while hour <= window.end:
        hours.append(hour)
        hour += timedelta(hours=1)
    return tuple(hours)


def _windows_overlap(left: Window, right: Window) -> bool:
    return left.start <= right.end and right.start <= left.end


def select_window_pairs_within_budget(
    pairs: Sequence[PullWindowPair],
    *,
    cost_for_keys: Callable[[Iterable[str]], float],
    budget_usd: float = PULL_BUDGET_USD,
) -> BudgetSelection:
    """Keep the strongest merged event/baseline pairs under a hard cost gate.

    Merged windows are indivisible because their hourly objects are shared by
    every constituent event.  They are ranked by the maximum pre-registered
    burst strength (rate multiple times sigma-displacement) of their events,
    then by stable market/start/pair-id tie breakers.  No download occurs here.
    """

    if not math.isfinite(budget_usd) or budget_usd <= 0:
        raise ValueError("budget_usd must be finite and positive")
    ordered = sorted(
        pairs,
        key=lambda pair: (
            -pair.burst_strength,
            pair.market,
            pair.event.start,
            pair.pair_id,
        ),
    )
    all_keys = [key for pair in ordered for key in pair.object_keys]
    original_cost = float(cost_for_keys(all_keys))
    if original_cost <= budget_usd:
        return BudgetSelection(
            selected_pairs=tuple(ordered),
            dropped_pairs=(),
            original_cost_usd=original_cost,
            selected_cost_usd=original_cost,
            downscoped=False,
            coverage_cut_reason=None,
        )

    selected: list[PullWindowPair] = []
    selected_cost = 0.0
    selected_keys: list[str] = []
    for pair in ordered:
        candidate_keys = [*selected_keys, *pair.object_keys]
        candidate_cost = float(cost_for_keys(candidate_keys))
        if candidate_cost <= budget_usd:
            selected.append(pair)
            selected_keys = candidate_keys
            selected_cost = candidate_cost
        else:
            continue

    selected_ids = {pair.pair_id for pair in selected}
    dropped = [pair for pair in ordered if pair.pair_id not in selected_ids]
    return BudgetSelection(
        selected_pairs=tuple(selected),
        dropped_pairs=tuple(dropped),
        original_cost_usd=original_cost,
        selected_cost_usd=selected_cost,
        downscoped=True,
        coverage_cut_reason=f"T7 pull estimate exceeded ${budget_usd:.2f}",
    )


def compute_cascade_anatomy(
    events: pl.DataFrame,
    l1: pl.DataFrame,
    depth: pl.DataFrame,
    *,
    reversion_limit: timedelta = timedelta(minutes=30),
) -> pl.DataFrame:
    """Compute causal pre-baselines and paper-defined anatomy per tagged event.

    The baseline is the arithmetic mean of executable-quote microprices in the
    trailing minute, with the event start excluded.  The adverse extreme is
    searched only from event start through event end.  Reversion is searched
    from that extreme through ``event end + reversion_limit``.  Displayed depth
    is the latest full reconstructed state known no later than event start and
    is walked from touch until the tagged aggressor size is exhausted.
    """

    required_events = {
        "event_id",
        "market",
        "start_time",
        "end_time",
        "direction",
        "aggressor_size",
        "tag_label",
    }
    required_depth = {"time_exchange", "side", "level", "price", "size"}
    missing_events = sorted(required_events - set(events.columns))
    missing_depth = sorted(required_depth - set(depth.columns))
    if missing_events:
        raise ValueError(f"events missing required columns: {missing_events}")
    if missing_depth:
        raise ValueError(f"depth missing required columns: {missing_depth}")
    if events.filter(pl.col("tag_label") != PROXY_LABEL).height:
        raise ValueError("Study 2 anatomy accepts only proxy-tagged events")
    micro = microprice_frame(l1).sort("time_exchange")
    rows: list[dict[str, object]] = []
    for event in events.sort(["market", "start_time"]).iter_rows(named=True):
        start = event["start_time"]
        end = event["end_time"]
        if end < start:
            raise ValueError(f"event {event['event_id']} ends before it starts")
        direction = str(event["direction"]).upper()
        if direction not in {"BUY", "SELL"}:
            raise ValueError(f"unsupported event direction {direction!r}")

        pre = micro.filter(
            (pl.col("time_exchange") >= start - timedelta(minutes=1))
            & (pl.col("time_exchange") < start)
        )
        during = micro.filter(
            (pl.col("time_exchange") >= start)
            & (pl.col("time_exchange") <= end)
        )
        pre_mean = None if pre.is_empty() else float(pre["microprice"].mean())
        overshoot_time: datetime | None = None
        overshoot_price: float | None = None
        overshoot_bps: float | None = None
        reversion_half_life: float | None = None
        reversion_censored = False
        zero_overshoot = False
        if pre_mean is not None and not during.is_empty():
            extreme_value = (
                float(during["microprice"].min())
                if direction == "SELL"
                else float(during["microprice"].max())
            )
            extreme_rows = during.filter(pl.col("microprice") == extreme_value)
            overshoot_time = extreme_rows["time_exchange"][0]
            signed = (
                pre_mean - extreme_value
                if direction == "SELL"
                else extreme_value - pre_mean
            )
            overshoot_price = max(0.0, signed)
            overshoot_bps = overshoot_price / pre_mean * 10_000.0
            if overshoot_price <= 0.0:
                zero_overshoot = True
            else:
                target = (
                    pre_mean - overshoot_price / 2.0
                    if direction == "SELL"
                    else pre_mean + overshoot_price / 2.0
                )
                after_extreme = micro.filter(
                    (pl.col("time_exchange") >= overshoot_time)
                    & (pl.col("time_exchange") <= end + reversion_limit)
                    & (
                        (pl.col("microprice") >= target)
                        if direction == "SELL"
                        else (pl.col("microprice") <= target)
                    )
                )
                if after_extreme.is_empty():
                    reversion_censored = True
                else:
                    reversion_half_life = (
                        after_extreme["time_exchange"][0] - overshoot_time
                    ).total_seconds()

        levels_consumed, size_consumed, size_available, shortfall, depth_time = (
            _walk_pre_event_depth(
                depth,
                start=start,
                direction=direction,
                aggressor_size=float(event["aggressor_size"]),
            )
        )
        rows.append(
            {
                **event,
                "pre_event_microprice_mean": pre_mean,
                "pre_event_observation_count": pre.height,
                "overshoot_price": overshoot_price,
                "overshoot_bps": overshoot_bps,
                "overshoot_time": overshoot_time,
                "reversion_half_life_seconds": reversion_half_life,
                "reversion_censored": reversion_censored,
                "zero_overshoot": zero_overshoot,
                "duration_seconds": (end - start).total_seconds(),
                "depth_snapshot_time": depth_time,
                "depth_levels_consumed": levels_consumed,
                "depth_size_consumed": size_consumed,
                "depth_size_available": size_available,
                "depth_size_shortfall": shortfall,
            }
        )
    return pl.DataFrame(rows) if rows else _empty_anatomy(events)


def _walk_pre_event_depth(
    depth: pl.DataFrame,
    *,
    start: datetime,
    direction: str,
    aggressor_size: float,
) -> tuple[int | None, float | None, float | None, float | None, datetime | None]:
    if not math.isfinite(aggressor_size) or aggressor_size < 0:
        raise ValueError("aggressor_size must be finite and non-negative")
    known = depth.filter(pl.col("time_exchange") <= start)
    if known.is_empty():
        return None, None, None, None, None
    depth_time = known["time_exchange"].max()
    side = "bid" if direction == "SELL" else "ask"
    levels = known.filter(
        (pl.col("time_exchange") == depth_time) & (pl.col("side") == side)
    ).sort("level")
    if levels.is_empty():
        return 0, 0.0, 0.0, aggressor_size, depth_time
    available = float(levels["size"].sum())
    remaining = aggressor_size
    consumed = 0.0
    level_count = 0
    for size in levels["size"]:
        if remaining <= 0:
            break
        numeric = float(size)
        take = min(remaining, numeric)
        if take > 0:
            level_count += 1
            consumed += take
            remaining -= take
    return level_count, consumed, available, max(0.0, remaining), depth_time


def _empty_anatomy(events: pl.DataFrame) -> pl.DataFrame:
    schema = dict(events.schema)
    schema.update(
        {
            "pre_event_microprice_mean": pl.Float64,
            "pre_event_observation_count": pl.Int64,
            "overshoot_price": pl.Float64,
            "overshoot_bps": pl.Float64,
            "overshoot_time": pl.Datetime("ns"),
            "reversion_half_life_seconds": pl.Float64,
            "reversion_censored": pl.Boolean,
            "zero_overshoot": pl.Boolean,
            "duration_seconds": pl.Float64,
            "depth_snapshot_time": pl.Datetime("ns"),
            "depth_levels_consumed": pl.Int64,
            "depth_size_consumed": pl.Float64,
            "depth_size_available": pl.Float64,
            "depth_size_shortfall": pl.Float64,
        }
    )
    return pl.DataFrame(schema=schema)
