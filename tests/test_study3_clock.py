from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl

from charybdis.study3_clock import (
    aggregate_l4_trades_to_1m,
    bracket_side,
    harvest_1m_candles,
    inside_bracket_return,
    select_candle_cache_file,
    settlement_control_window,
    wallet_window_events,
)


def test_l4_trades_aggregate_to_minute_first_open_last_close_by_exchange_time() -> None:
    trades = pl.DataFrame(
        {
            "time_exchange": [
                datetime(2026, 7, 1, 11, 59, 59),
                datetime(2026, 7, 1, 11, 59, 1),
                datetime(2026, 7, 1, 12, 0, 1),
                datetime(2026, 7, 1, 12, 0, 58),
            ],
            "price": [102.0, 100.0, 103.0, 104.0],
        }
    )

    bars = aggregate_l4_trades_to_1m(trades)

    assert bars.select("open", "close").rows() == [(100.0, 102.0), (103.0, 104.0)]
    assert bars["time_close"].to_list() == [
        datetime(2026, 7, 1, 11, 59, 59),
        datetime(2026, 7, 1, 12, 0, 58),
    ]


def test_bracket_assignment_across_settlement_boundary_is_explicit() -> None:
    settlement = datetime(2026, 7, 1, 12)

    assert bracket_side(settlement - timedelta(seconds=1), settlement) == "pre"
    assert bracket_side(settlement, settlement) == "settlement_instant"
    assert bracket_side(settlement + timedelta(seconds=1), settlement) == "post"


def test_production_bracket_return_single_candle_and_settlement_boundary() -> None:
    settlement = datetime(2026, 7, 1, 12)
    times = [
        settlement - timedelta(seconds=1),
        settlement + timedelta(seconds=1),
    ]
    opens = [100.0, 200.0]
    closes = [110.0, 220.0]

    pre, pre_n = inside_bracket_return(
        times, opens, closes, settlement - timedelta(minutes=1), settlement
    )
    post, post_n = inside_bracket_return(
        times, opens, closes, settlement, settlement + timedelta(minutes=1)
    )

    assert (pre_n, post_n) == (1, 1)
    assert pre == pl.Series([1.1]).log()[0]
    assert post == pl.Series([1.1]).log()[0]


def test_plus_30m_control_never_overlaps_adjacent_settlement_windows() -> None:
    settlement = datetime(2026, 7, 1, 12)
    real_windows = [
        (other - timedelta(minutes=10), other + timedelta(minutes=10))
        for other in (
            settlement - timedelta(hours=1), settlement, settlement + timedelta(hours=1)
        )
    ]

    for bracket in (-10, -5, -1, 1, 5, 10):
        control = settlement_control_window(settlement, bracket)
        assert all(
            control.end <= real_start or real_end <= control.start
            for real_start, real_end in real_windows
        )


def test_report_describes_actual_plus_30m_placebo_not_study2_matching() -> None:
    report = Path("docs/reports/study3_funding_clock_2026-07-10.md").read_text()

    assert "within-hour placebo" in report
    assert "shares hour-level shocks" in report
    assert "nearest-calendar-day" not in report


def test_candle_cache_selection_is_widest_then_latest_and_missing_is_none(tmp_path) -> None:
    narrow = tmp_path / "xyz__TEST_202607010000_202607020000_1m.parquet"
    widest_old = tmp_path / "xyz__TEST_202606010000_202607010000_1m.parquet"
    widest_latest = tmp_path / "xyz__TEST_202606020000_202607020000_1m.parquet"
    for path in (narrow, widest_latest, widest_old):
        path.touch()

    assert select_candle_cache_file([narrow, widest_latest, widest_old]) == widest_latest
    assert select_candle_cache_file([]) is None


def test_wallet_share_has_matched_plus_30m_baseline_and_paired_difference() -> None:
    settlement = datetime(2026, 7, 1, 12)
    trades = pl.DataFrame(
        {
            "market": ["xyz:TEST"] * 6,
            "time_exchange": [
                settlement - timedelta(minutes=5), settlement + timedelta(minutes=5),
                settlement - timedelta(minutes=4), settlement + timedelta(minutes=4),
                settlement + timedelta(minutes=25), settlement + timedelta(minutes=35),
            ],
            "user_taker": ["event-short", "event-short", "event-other", "event-other", "control-short", "control-short"],
            "signed_notional": [-10.0, 10.0, -10.0, -10.0, -20.0, 20.0],
        }
    )

    events, _ = wallet_window_events(trades)
    row = events.row(0, named=True)

    assert row["short_open_close_share"] == 0.5
    assert row["baseline_short_open_close_share"] == 1.0
    assert row["short_open_close_share_difference"] == -0.5


def test_1m_harvest_second_run_makes_zero_client_calls(tmp_path) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        def candle_snapshot(self, market, interval, start_ms, end_ms):
            self.calls += 1
            return pl.DataFrame(
                {
                    "market": [market],
                    "interval": [interval],
                    "open_time_ms": [start_ms],
                    "close_time_ms": [start_ms + 59_999],
                    "time_open": [datetime(2026, 7, 1)],
                    "open": [100.0],
                    "high": [100.0],
                    "low": [100.0],
                    "close": [100.0],
                    "volume": [1.0],
                    "trade_count": [1],
                }
            )

    client = FakeClient()
    kwargs = {
        "client": client,
        "markets": ["xyz:TEST"],
        "start": datetime(2026, 7, 1),
        "end": datetime(2026, 7, 1, 1),
        "output_dir": tmp_path,
    }
    first = harvest_1m_candles(**kwargs)
    assert client.calls == 1
    second = harvest_1m_candles(**kwargs)

    assert first.actual_client_calls == 1
    assert second.actual_client_calls == 0
    assert client.calls == 1
