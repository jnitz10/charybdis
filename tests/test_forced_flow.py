from __future__ import annotations

from datetime import datetime, timedelta
import math
from pathlib import Path
from statistics import median, pstdev
import struct

import polars as pl
import pytest

from charybdis.forced_flow import (
    _aggregate_trade_frame,
    _detect_from_aggregates,
    detect_proxy_events,
)


REPORT_PATH = Path("data/reports/forced_flow_events_proxy.parquet")


def _trade(
    when: datetime,
    *,
    price: float,
    side: str,
    wallet: str,
    size: float = 1.0,
) -> dict[str, object]:
    return {
        "market": "SKHX",
        "time_exchange": when,
        "price": price,
        "base_amount": size,
        "taker_side": side,
        "user_taker": wallet,
    }


def _history(*, burst: bool) -> tuple[pl.DataFrame, datetime]:
    start = datetime(2026, 1, 1)
    rows: list[dict[str, object]] = []
    for minute in range(65):
        close = 100.05 if minute % 2 == 0 else 99.95
        at = start + timedelta(minutes=minute)
        rows.append(
            _trade(at + timedelta(seconds=5), price=close + 0.01, side="BUY", wallet="b")
        )
        rows.append(
            _trade(at + timedelta(seconds=35), price=close, side="SELL", wallet="s")
        )

    candidate = start + timedelta(minutes=65)
    if burst:
        for index in range(7):
            rows.append(
                _trade(
                    candidate + timedelta(seconds=index * 8),
                    price=99.0 - index,
                    side="SELL",
                    wallet="forced-wallet",
                    size=2.0,
                )
            )
    else:
        rows.extend(
            [
                _trade(
                    candidate + timedelta(seconds=8),
                    price=99.96,
                    side="SELL",
                    wallet="calm-wallet",
                ),
                _trade(
                    candidate + timedelta(seconds=38),
                    price=99.95,
                    side="SELL",
                    wallet="calm-wallet",
                ),
            ]
        )
    return pl.DataFrame(rows), candidate


def test_proxy_heuristic_fires_on_burst_fixture() -> None:
    trades, candidate = _history(burst=True)

    events = detect_proxy_events(trades)

    tagged = events.filter(pl.col("start_time") == candidate)
    assert tagged.height == 1
    row = tagged.row(0, named=True)
    assert row["direction"] == "SELL"
    assert row["aggressor_size"] == pytest.approx(14.0)
    assert row["wallets"] == ["forced-wallet"]
    assert row["trade_count"] >= 3 * row["trailing_median_trade_rate"]
    assert row["price_displacement"] >= 3 * row["trailing_return_sigma"]
    assert row["trigger_source"] == "proxy"
    assert row["tag_label"] == "proxy-tagged"


def test_proxy_heuristic_is_silent_on_calm_fixture() -> None:
    trades, _ = _history(burst=False)

    assert detect_proxy_events(trades).is_empty()


def test_proxy_trailing_windows_have_no_lookahead() -> None:
    start = datetime(2026, 1, 1)
    prior_counts = [1] * 30 + [2] * 30
    prior_closes = [100.0 if minute % 2 == 0 else 101.0 for minute in range(60)]
    rows: list[dict[str, object]] = []
    for minute, (count, close) in enumerate(zip(prior_counts, prior_closes)):
        at = start + timedelta(minutes=minute)
        for index in range(count):
            rows.append(
                _trade(
                    at + timedelta(seconds=5 + index),
                    price=close,
                    side="SELL",
                    wallet=f"history-{minute}-{index}",
                )
            )

    candidate = start + timedelta(minutes=60)
    candidate_count = 7
    for index in range(candidate_count):
        rows.append(
            _trade(
                candidate + timedelta(seconds=index),
                price=90.0,
                side="SELL",
                wallet="candidate-wallet",
            )
        )
    future = candidate + timedelta(minutes=1)
    for index in range(20):
        rows.append(
            _trade(
                future + timedelta(seconds=index),
                price=70.0,
                side="SELL",
                wallet="future-wallet",
            )
        )

    full = detect_proxy_events(pl.DataFrame(rows)).filter(
        pl.col("start_time") == candidate
    )
    without_future = detect_proxy_events(
        pl.DataFrame([row for row in rows if row["time_exchange"] < future])
    ).filter(pl.col("start_time") == candidate)

    assert full.height == without_future.height == 1
    baseline_columns = ["trailing_median_trade_rate", "trailing_return_sigma"]
    full_baseline = full.select(baseline_columns).row(0)
    truncated_baseline = without_future.select(baseline_columns).row(0)
    assert struct.pack("!dd", *full_baseline) == struct.pack(
        "!dd", *truncated_baseline
    )

    prior_returns = [0.0] + [
        math.log(current / previous)
        for previous, current in zip(prior_closes, prior_closes[1:])
    ]
    expected_rate = float(median(prior_counts))
    expected_sigma = float(pstdev(prior_returns))
    row = full.row(0, named=True)
    assert row["trailing_median_trade_rate"] == expected_rate
    assert row["trailing_return_sigma"] == expected_sigma

    candidate_return = math.log(90.0 / prior_closes[-1])
    with_candidate_rate = float(median((prior_counts + [candidate_count])[-60:]))
    with_candidate_sigma = float(
        pstdev((prior_returns + [candidate_return])[-60:])
    )
    assert expected_rate != with_candidate_rate
    assert expected_sigma != with_candidate_sigma


def test_non_positive_prices_are_excluded_before_aggregation() -> None:
    start = datetime(2026, 1, 1)
    trades = pl.DataFrame(
        [
            _trade(start + timedelta(seconds=1), price=100.0, side="BUY", wallet="ok"),
            _trade(
                start + timedelta(minutes=1, seconds=2),
                price=0.0,
                side="BUY",
                wallet="zero",
            ),
            _trade(
                start + timedelta(minutes=2, seconds=3),
                price=-1.0,
                side="BUY",
                wallet="negative",
            ),
        ]
    )

    directional, closes = _aggregate_trade_frame(trades)

    assert directional["trade_count"].to_list() == [1]
    assert closes["close"].to_list() == [100.0]
    assert detect_proxy_events(trades).is_empty()


def test_sparse_zero_median_burst_abstains_and_is_counted() -> None:
    start = datetime(2026, 1, 1)
    rows: list[dict[str, object]] = []
    for minute in range(0, 60, 4):
        rows.append(
            _trade(
                start + timedelta(minutes=minute, seconds=5),
                price=100.0 if minute % 8 == 0 else 101.0,
                side="SELL",
                wallet=f"sparse-{minute}",
            )
        )
    candidate = start + timedelta(minutes=60)
    for index in range(7):
        rows.append(
            _trade(
                candidate + timedelta(seconds=index),
                price=90.0,
                side="SELL",
                wallet="burst-wallet",
            )
        )
    diagnostics: dict[str, int] = {}

    events = detect_proxy_events(pl.DataFrame(rows), diagnostics=diagnostics)

    assert events.is_empty()
    assert diagnostics == {
        "total": 1,
        "zero_baseline_rate": 1,
        "zero_return_sigma": 0,
    }


def test_duplicate_directional_buckets_are_summed_before_detection() -> None:
    history, candidate = _history(burst=False)
    history = history.filter(pl.col("time_exchange") < candidate)
    first_candidate = pl.DataFrame(
        [
            _trade(
                candidate + timedelta(seconds=index),
                price=90.0,
                side="SELL",
                wallet="forced-wallet",
            )
            for index in range(3)
        ]
    )
    second_candidate = pl.DataFrame(
        [
            _trade(
                candidate + timedelta(seconds=10 + index),
                price=89.0,
                side="SELL",
                wallet="forced-wallet",
            )
            for index in range(4)
        ]
    )
    first_directional, first_closes = _aggregate_trade_frame(
        pl.concat([history, first_candidate])
    )
    second_directional, second_closes = _aggregate_trade_frame(second_candidate)

    events = _detect_from_aggregates(
        pl.concat([second_directional, first_directional], how="vertical_relaxed"),
        pl.concat([second_closes, first_closes], how="vertical_relaxed"),
    )

    tagged = events.filter(pl.col("start_time") == candidate)
    assert tagged.height == 1
    row = tagged.row(0, named=True)
    assert row["trade_count"] == 7
    assert row["price_displacement"] == pytest.approx(math.log(100.05 / 89.0))


def test_real_proxy_event_table_has_detected_event() -> None:
    assert REPORT_PATH.exists(), "run the bounded SKHX/SMSN event-table build"
    events = pl.read_parquet(REPORT_PATH)
    assert events.height >= 1
    assert set(events["market"].unique()) <= {"SKHX", "SMSN"}
    assert events["tag_label"].unique().to_list() == ["proxy-tagged"]
