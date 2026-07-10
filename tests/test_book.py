from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from charybdis.book import iter_book_snapshots, reconstruct_depth, reconstruct_l1
from charybdis.loaders import scan_book_events


BOOK = (
    Path(__file__).parent
    / "fixtures/T-LIMITBOOK_FULL/D-20260408/E-HYPERLIQUID/"
    / "IDDI-46924264+SC-HYPERLIQUID_DPERP_KM_SMALL2000_USDC"
    "+S-KM__003ASMALL2000.csv.gz"
)
# Synthetic: CoinAPI-shaped tape with a rare mid-stream re-snapshot.
MIDSTREAM_RESNAPSHOT = Path(__file__).parent / "fixtures/synthetic_midstream_resnapshot.csv"


def _events() -> pl.DataFrame:
    return scan_book_events(
        BOOK,
        columns=("time_exchange", "update_type", "is_buy", "entry_px", "entry_sx"),
    ).collect()


def test_real_snapshot_and_increments_match_hand_computed_l1() -> None:
    l1 = reconstruct_l1(_events())

    assert l1.select(
        "best_bid_px", "best_bid_sx", "best_ask_px", "best_ask_sx"
    ).rows()[:5] == [
        (261.39, 1186.192, 261.75, 0.24),
        (261.39, 1186.192, 261.59, 1186.192),
        (260.5, 0.18, 261.75, 0.24),
        (260.58, 2372.385, 261.75, 0.24),
        (260.58, 2372.385, 261.75, 0.24),
    ]
    assert l1[-1, "best_bid_sx"] == 4744.77


def test_depth_series_exposes_sorted_levels_after_opening_snapshot() -> None:
    depth = reconstruct_depth(_events(), levels=2)
    opening_time = depth[0, "time_exchange"]

    assert depth.filter(pl.col("time_exchange") == opening_time).select(
        "side", "level", "price", "size"
    ).rows() == [
        ("bid", 1, 261.39, 1186.192),
        ("bid", 2, 261.25, 38.288),
        ("ask", 1, 261.75, 0.24),
        ("ask", 2, 261.78, 48.221),
    ]


def test_book_state_before_cutoff_is_independent_of_future_rows() -> None:
    events = _events()
    cutoff = events[46, "time_exchange"]
    past = events.filter(pl.col("time_exchange") <= cutoff)

    from_past_only = reconstruct_l1(past)
    from_full_tape = reconstruct_l1(events).filter(pl.col("time_exchange") <= cutoff)

    assert from_past_only.equals(from_full_tape)


def test_snapshot_run_spanning_timestamps_keeps_all_levels() -> None:
    first_time = datetime(2026, 4, 8, 0, 0, 0)
    events = [
        {
            "time_exchange": first_time,
            "update_type": "SNAPSHOT",
            "is_buy": True,
            "entry_px": 100.0,
            "entry_sx": 2.0,
        },
        {
            "time_exchange": first_time + timedelta(microseconds=1),
            "update_type": "SNAPSHOT",
            "is_buy": True,
            "entry_px": 99.0,
            "entry_sx": 3.0,
        },
    ]

    snapshots = list(iter_book_snapshots(events))

    assert snapshots[-1].bids == ((100.0, 2.0), (99.0, 3.0))


def test_book_batches_reject_decreasing_exchange_timestamps() -> None:
    first_time = datetime(2026, 4, 8, 0, 0, 0)

    def event(timestamp: datetime, price: float) -> dict[str, object]:
        return {
            "time_exchange": timestamp,
            "update_type": "ADD",
            "is_buy": True,
            "entry_px": price,
            "entry_sx": 1.0,
        }

    monotonic = [
        event(first_time, 100.0),
        event(first_time, 99.0),
        event(first_time + timedelta(microseconds=1), 98.0),
    ]
    assert [snapshot.time_exchange for snapshot in iter_book_snapshots(monotonic)] == [
        first_time,
        first_time + timedelta(microseconds=1),
    ]

    decreasing = [
        event(first_time + timedelta(microseconds=1), 100.0),
        event(first_time, 99.0),
    ]
    with pytest.raises(ValueError, match="non-monotonic time_exchange"):
        list(iter_book_snapshots(decreasing))


def test_midstream_resnapshot_replaces_prior_book_at_l1_checkpoints() -> None:
    events = scan_book_events(
        MIDSTREAM_RESNAPSHOT,
        era="l4",
        columns=("time_exchange", "update_type", "is_buy", "entry_px", "entry_sx"),
    ).collect()

    l1 = reconstruct_l1(events)
    checkpoints = l1.select(
        "best_bid_px", "best_bid_sx", "best_ask_px", "best_ask_sx"
    ).rows()

    assert [checkpoints[index] for index in (0, 1, 3)] == [
        (100.0, 5.0, 101.0, 6.0),
        (100.0, 3.0, 101.0, 6.0),
        (90.0, 7.0, 110.0, 9.0),
    ]
