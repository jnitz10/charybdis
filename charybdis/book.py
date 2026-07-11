"""Bounded-state reconstruction of L2 CoinAPI book events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Any, Iterable, Iterator, Mapping

import polars as pl


@dataclass(frozen=True)
class BookSnapshot:
    time_exchange: datetime
    bids: tuple[tuple[float, float], ...]
    asks: tuple[tuple[float, float], ...]

    @property
    def best_bid(self) -> tuple[float | None, float | None]:
        return self.bids[0] if self.bids else (None, None)

    @property
    def best_ask(self) -> tuple[float | None, float | None]:
        return self.asks[0] if self.asks else (None, None)


class BookReconstructor:
    """Apply one event at a time while retaining only current book state."""

    def __init__(self) -> None:
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self._in_snapshot = False

    def apply(self, event: Mapping[str, Any]) -> None:
        update_type = str(event["update_type"]).upper()
        timestamp = event["time_exchange"]
        price = float(event["entry_px"])
        size = float(event["entry_sx"])
        if size < 0:
            raise ValueError(f"negative book size {size} at {timestamp}")

        if update_type == "SNAPSHOT":
            if not self._in_snapshot:
                self.bids.clear()
                self.asks.clear()
                self._in_snapshot = True
            self._set_level(self._side(event["is_buy"]), price, size)
            return

        self._in_snapshot = False
        side = self._side(event["is_buy"])
        if update_type == "ADD":
            self._set_level(side, price, side.get(price, 0.0) + size)
        elif update_type == "SUB":
            if price not in side:
                raise ValueError(f"SUB for absent level {price} at {timestamp}")
            remaining = side[price] - size
            tolerance = max(1e-12, abs(side[price]) * 1e-12)
            if remaining < -tolerance:
                raise ValueError(
                    f"SUB {size} exceeds level {price} size {side[price]} at {timestamp}"
                )
            self._set_level(side, price, max(0.0, remaining))
        elif update_type in {"SET", "CHANGE", "UPDATE"}:
            self._set_level(side, price, size)
        elif update_type in {"DELETE", "REMOVE"}:
            side.pop(price, None)
        else:
            raise ValueError(f"unsupported book update_type {update_type!r}")

    def snapshot(self, timestamp: datetime) -> BookSnapshot:
        return BookSnapshot(
            time_exchange=timestamp,
            bids=tuple(sorted(self.bids.items(), reverse=True)),
            asks=tuple(sorted(self.asks.items())),
        )

    def _side(self, is_buy: object) -> dict[float, float]:
        if isinstance(is_buy, str):
            buy = is_buy.strip().lower() in {"1", "true", "t", "yes"}
        else:
            buy = bool(is_buy)
        return self.bids if buy else self.asks

    @staticmethod
    def _set_level(side: dict[float, float], price: float, size: float) -> None:
        if size <= 0:
            side.pop(price, None)
        else:
            side[price] = size


@dataclass(frozen=True)
class _L4Order:
    is_buy: bool
    price: float
    size: float


class L4OrderBookReconstructor:
    """Reconstruct aggregate depth from order-level L4 snapshot/increments.

    CoinAPI L4 rows identify individual orders.  Order state is therefore kept
    by ``order_id`` and a second, aggregate price-level map is adjusted with
    every order mutation.  This avoids re-summing every live order at every
    timestamp while preserving the bounded-current-state property of the L2
    reconstructor.
    """

    def __init__(self) -> None:
        self.orders: dict[str, _L4Order] = {}
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self._in_snapshot = False

    def apply(self, event: Mapping[str, Any]) -> None:
        update_type = str(event["update_type"]).upper()
        timestamp = event["time_exchange"]
        raw_order_id = event.get("order_id")
        order_id = "" if raw_order_id is None else str(raw_order_id)
        if not order_id:
            raise ValueError(f"L4 row has no order_id at {timestamp}")

        if update_type == "SNAPSHOT":
            if not self._in_snapshot:
                self._clear()
                self._in_snapshot = True
            if not self._is_live_resting_order(event):
                return
            self._replace(
                order_id,
                self._side_value(event["is_buy"]),
                float(event["entry_px"]),
                float(event["entry_sx"]),
                timestamp,
            )
            return

        self._in_snapshot = False
        if update_type == "ADD":
            if not self._is_live_resting_order(event):
                self._remove(order_id)
                return
            is_buy = self._side_value(event["is_buy"])
            price = float(event["entry_px"])
            size = float(event["entry_sx"])
            prior = self.orders.get(order_id)
            if prior is not None and (prior.is_buy != is_buy or prior.price != price):
                raise ValueError(
                    f"ADD changes side/price for live order {order_id!r} at {timestamp}"
                )
            new_size = size if prior is None else prior.size + size
            self._replace(order_id, is_buy, price, new_size, timestamp)
        elif update_type == "SUB":
            size = float(event["entry_sx"])
            if not math.isfinite(size) or size < 0:
                raise ValueError(f"invalid L4 SUB size {size} at {timestamp}")
            prior = self.orders.get(order_id)
            if prior is None:
                raise ValueError(f"SUB for absent L4 order {order_id!r} at {timestamp}")
            tolerance = max(1e-12, prior.size * 1e-12)
            remaining = prior.size - size
            if remaining < -tolerance:
                raise ValueError(
                    f"SUB {size} exceeds L4 order {order_id!r} size "
                    f"{prior.size} at {timestamp}"
                )
            self._replace(
                order_id,
                prior.is_buy,
                prior.price,
                max(0.0, remaining),
                timestamp,
            )
        elif update_type in {"SET", "CHANGE", "UPDATE"}:
            if not self._is_live_resting_order(event):
                self._remove(order_id)
                return
            self._replace(
                order_id,
                self._side_value(event["is_buy"]),
                float(event["entry_px"]),
                float(event["entry_sx"]),
                timestamp,
            )
        elif update_type in {"DELETE", "DELETE_IF_EXISTS", "REMOVE"}:
            self._remove(order_id)
        elif update_type in {"PENDING", "REJECTED"}:
            # Hyperliquid L4 emits lifecycle/status rows with the same schema.
            # They do not describe resting-depth mutations; SET/DELETE carries
            # the corresponding executable order-state transition.
            return
        else:
            raise ValueError(f"unsupported L4 book update_type {update_type!r}")

    def snapshot(self, timestamp: datetime) -> BookSnapshot:
        return BookSnapshot(
            time_exchange=timestamp,
            bids=tuple(sorted(self.bids.items(), reverse=True)),
            asks=tuple(sorted(self.asks.items())),
        )

    def _clear(self) -> None:
        self.orders.clear()
        self.bids.clear()
        self.asks.clear()

    @staticmethod
    def _side_value(value: object) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "t", "yes"}
        return bool(value)

    @staticmethod
    def _is_live_resting_order(event: Mapping[str, Any]) -> bool:
        raw_trigger = event.get("is_trigger")
        if isinstance(raw_trigger, str):
            is_trigger = raw_trigger.strip().lower() in {"1", "true", "t", "yes"}
        else:
            is_trigger = bool(raw_trigger)
        raw_order_type = event.get("order_type")
        order_type = None if raw_order_type is None else str(raw_order_type).strip().lower()
        raw_status = event.get("hl4_status")
        status = None if raw_status is None else str(raw_status).strip().upper()
        return (
            not is_trigger
            and order_type in {None, "limit"}
            and status in {None, "", "OPEN"}
        )

    def _replace(
        self,
        order_id: str,
        is_buy: bool,
        price: float,
        size: float,
        timestamp: object,
    ) -> None:
        if not math.isfinite(price) or price <= 0:
            raise ValueError(f"invalid L4 order price {price} at {timestamp}")
        if not math.isfinite(size) or size < 0:
            raise ValueError(f"invalid L4 order size {size} at {timestamp}")
        self._remove(order_id)
        if size == 0:
            return
        order = _L4Order(is_buy=is_buy, price=price, size=size)
        self.orders[order_id] = order
        self._adjust_level(order, size)

    def _remove(self, order_id: str) -> None:
        prior = self.orders.pop(order_id, None)
        if prior is not None:
            self._adjust_level(prior, -prior.size)

    def _adjust_level(self, order: _L4Order, delta: float) -> None:
        side = self.bids if order.is_buy else self.asks
        updated = side.get(order.price, 0.0) + delta
        tolerance = max(1e-12, abs(side.get(order.price, 0.0)) * 1e-12)
        if updated < -tolerance:
            raise ValueError(f"negative aggregate L4 depth at {order.price}")
        if updated <= tolerance:
            side.pop(order.price, None)
        else:
            side[order.price] = updated


def iter_book_snapshots(
    events: pl.DataFrame | Iterable[Mapping[str, Any]],
) -> Iterator[BookSnapshot]:
    """Yield state after each exchange-timestamp batch, without future-row use."""

    rows: Iterable[Mapping[str, Any]]
    if isinstance(events, pl.DataFrame):
        rows = events.iter_rows(named=True)
    else:
        rows = events

    book = BookReconstructor()
    current_time: datetime | None = None
    for event in rows:
        timestamp = event["time_exchange"]
        if current_time is not None and timestamp < current_time:
            raise ValueError(
                "non-monotonic time_exchange: "
                f"{timestamp!r} follows {current_time!r}"
            )
        if current_time is not None and timestamp != current_time:
            yield book.snapshot(current_time)
        current_time = timestamp
        book.apply(event)
    if current_time is not None:
        yield book.snapshot(current_time)


def iter_l4_book_snapshots(
    events: pl.DataFrame | Iterable[Mapping[str, Any]],
) -> Iterator[BookSnapshot]:
    """Yield aggregate L4 depth after each exchange-timestamp batch."""

    rows: Iterable[Mapping[str, Any]]
    if isinstance(events, pl.DataFrame):
        rows = events.iter_rows(named=True)
    else:
        rows = events

    book = L4OrderBookReconstructor()
    current_time: datetime | None = None
    for event in rows:
        timestamp = event["time_exchange"]
        if current_time is not None and timestamp < current_time:
            raise ValueError(
                "non-monotonic time_exchange: "
                f"{timestamp!r} follows {current_time!r}"
            )
        if current_time is not None and timestamp != current_time:
            yield book.snapshot(current_time)
        current_time = timestamp
        book.apply(event)
    if current_time is not None:
        yield book.snapshot(current_time)


def reconstruct_l1(
    events: pl.DataFrame | Iterable[Mapping[str, Any]],
) -> pl.DataFrame:
    """Return best bid/ask and displayed sizes after every event batch."""

    rows: list[dict[str, object]] = []
    for snapshot in iter_book_snapshots(events):
        bid_px, bid_sx = snapshot.best_bid
        ask_px, ask_sx = snapshot.best_ask
        rows.append(
            {
                "time_exchange": snapshot.time_exchange,
                "best_bid_px": bid_px,
                "best_bid_sx": bid_sx,
                "best_ask_px": ask_px,
                "best_ask_sx": ask_sx,
            }
        )
    return pl.DataFrame(
        rows,
        schema={
            "time_exchange": pl.Datetime("ns"),
            "best_bid_px": pl.Float64,
            "best_bid_sx": pl.Float64,
            "best_ask_px": pl.Float64,
            "best_ask_sx": pl.Float64,
        },
    )


def reconstruct_depth(
    events: pl.DataFrame | Iterable[Mapping[str, Any]],
    *,
    levels: int | None = None,
) -> pl.DataFrame:
    """Return a long depth series, ordered best-to-worst within each side."""

    if levels is not None and levels < 1:
        raise ValueError("levels must be positive or None")
    rows: list[dict[str, object]] = []
    for snapshot in iter_book_snapshots(events):
        for side_name, side in (("bid", snapshot.bids), ("ask", snapshot.asks)):
            selected = side if levels is None else side[:levels]
            for level, (price, size) in enumerate(selected, start=1):
                rows.append(
                    {
                        "time_exchange": snapshot.time_exchange,
                        "side": side_name,
                        "level": level,
                        "price": price,
                        "size": size,
                    }
                )
    return pl.DataFrame(
        rows,
        schema={
            "time_exchange": pl.Datetime("ns"),
            "side": pl.String,
            "level": pl.UInt32,
            "price": pl.Float64,
            "size": pl.Float64,
        },
    )


def reconstruct_l4_l1(
    events: pl.DataFrame | Iterable[Mapping[str, Any]],
) -> pl.DataFrame:
    """Return L1 derived from the order-level L4 snapshot/increment stream."""

    rows: list[dict[str, object]] = []
    for snapshot in iter_l4_book_snapshots(events):
        bid_px, bid_sx = snapshot.best_bid
        ask_px, ask_sx = snapshot.best_ask
        rows.append(
            {
                "time_exchange": snapshot.time_exchange,
                "best_bid_px": bid_px,
                "best_bid_sx": bid_sx,
                "best_ask_px": ask_px,
                "best_ask_sx": ask_sx,
            }
        )
    return pl.DataFrame(
        rows,
        schema={
            "time_exchange": pl.Datetime("ns"),
            "best_bid_px": pl.Float64,
            "best_bid_sx": pl.Float64,
            "best_ask_px": pl.Float64,
            "best_ask_sx": pl.Float64,
        },
    )


def reconstruct_l4_depth(
    events: pl.DataFrame | Iterable[Mapping[str, Any]],
    *,
    levels: int | None = None,
) -> pl.DataFrame:
    """Return long aggregate depth reconstructed from order-level L4 rows."""

    if levels is not None and levels < 1:
        raise ValueError("levels must be positive or None")
    rows: list[dict[str, object]] = []
    for snapshot in iter_l4_book_snapshots(events):
        for side_name, side in (("bid", snapshot.bids), ("ask", snapshot.asks)):
            selected = side if levels is None else side[:levels]
            for level, (price, size) in enumerate(selected, start=1):
                rows.append(
                    {
                        "time_exchange": snapshot.time_exchange,
                        "side": side_name,
                        "level": level,
                        "price": price,
                        "size": size,
                    }
                )
    return pl.DataFrame(
        rows,
        schema={
            "time_exchange": pl.Datetime("ns"),
            "side": pl.String,
            "level": pl.UInt32,
            "price": pl.Float64,
            "size": pl.Float64,
        },
    )


def sample_l4_depth(
    events: pl.DataFrame | Iterable[Mapping[str, Any]],
    sample_times: Iterable[datetime],
    *,
    levels: int | None = None,
) -> pl.DataFrame:
    """Sample order-level depth as-of requested times without future rows."""

    if levels is not None and levels < 1:
        raise ValueError("levels must be positive or None")
    queries = sorted(set(sample_times))
    if not queries:
        return _sampled_depth_frame([])
    rows = (
        list(events.iter_rows(named=True))
        if isinstance(events, pl.DataFrame)
        else list(events)
    )
    if any(
        current["time_exchange"] < previous["time_exchange"]
        for previous, current in zip(rows, rows[1:])
    ):
        raise ValueError("L4 events must be monotonic for as-of sampling")
    book = L4OrderBookReconstructor()
    event_index = 0
    source_time: datetime | None = None
    sampled: list[dict[str, object]] = []
    for query in queries:
        while event_index < len(rows) and rows[event_index]["time_exchange"] <= query:
            timestamp = rows[event_index]["time_exchange"]
            while (
                event_index < len(rows)
                and rows[event_index]["time_exchange"] == timestamp
            ):
                book.apply(rows[event_index])
                event_index += 1
            source_time = timestamp
        if source_time is None:
            continue
        snapshot = book.snapshot(source_time)
        for side_name, side in (("bid", snapshot.bids), ("ask", snapshot.asks)):
            selected = side if levels is None else side[:levels]
            for level, (price, size) in enumerate(selected, start=1):
                sampled.append(
                    {
                        "time_exchange": query,
                        "depth_source_time": source_time,
                        "side": side_name,
                        "level": level,
                        "price": price,
                        "size": size,
                    }
                )
    return _sampled_depth_frame(sampled)


def _sampled_depth_frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(
        rows,
        schema={
            "time_exchange": pl.Datetime("ns"),
            "depth_source_time": pl.Datetime("ns"),
            "side": pl.String,
            "level": pl.UInt32,
            "price": pl.Float64,
            "size": pl.Float64,
        },
    )
