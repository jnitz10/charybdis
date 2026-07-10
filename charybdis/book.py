"""Bounded-state reconstruction of L2 CoinAPI book events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
