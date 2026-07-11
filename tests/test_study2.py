from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl
import pytest

from charybdis.book import reconstruct_l4_depth, reconstruct_l4_l1
from charybdis.run_study2 import (
    _book_columns_for_schema,
    _matched_pair_fills,
    _quote_coverage_summary,
)
from charybdis.study2 import (
    PullWindowPair,
    Window,
    compute_cascade_anatomy,
    select_window_pairs_within_budget,
)


BASE = datetime(2026, 7, 1, 12, 0)


def _l4_event(
    seconds: float,
    update_type: str,
    order_id: str,
    is_buy: bool,
    price: float,
    size: float,
    *,
    is_trigger: bool = False,
    order_type: str = "Limit",
    hl4_status: str | None = None,
) -> dict[str, object]:
    return {
        "time_exchange": BASE + timedelta(seconds=seconds),
        "update_type": update_type,
        "order_id": order_id,
        "is_buy": is_buy,
        "entry_px": price,
        "entry_sx": size,
        "is_trigger": is_trigger,
        "order_type": order_type,
        "hl4_status": (
            hl4_status
            if hl4_status is not None
            else (None if update_type == "SNAPSHOT" else "OPEN")
        ),
    }


def test_l4_order_book_reconstructs_depth_across_snapshot_boundary() -> None:
    events = [
        _l4_event(0, "SNAPSHOT", "bid-1", True, 100.0, 2.0),
        _l4_event(0, "SNAPSHOT", "bid-2", True, 99.0, 3.0),
        _l4_event(0, "SNAPSHOT", "ask-1", False, 101.0, 1.0),
        _l4_event(1, "SUB", "bid-1", True, 100.0, 0.5),
        _l4_event(1, "ADD", "ask-2", False, 102.0, 4.0),
        # A fresh snapshot must discard every order from the prior state.
        _l4_event(2, "SNAPSHOT", "new-bid", True, 98.0, 5.0),
        _l4_event(2, "SNAPSHOT", "new-ask", False, 99.0, 2.0),
    ]

    depth = reconstruct_l4_depth(events)
    l1 = reconstruct_l4_l1(events)

    assert depth.filter(pl.col("time_exchange") == BASE).select(
        "side", "level", "price", "size"
    ).rows() == [
        ("bid", 1, 100.0, 2.0),
        ("bid", 2, 99.0, 3.0),
        ("ask", 1, 101.0, 1.0),
    ]
    assert depth.filter(pl.col("time_exchange") == BASE + timedelta(seconds=1)).select(
        "side", "level", "price", "size"
    ).rows() == [
        ("bid", 1, 100.0, 1.5),
        ("bid", 2, 99.0, 3.0),
        ("ask", 1, 101.0, 1.0),
        ("ask", 2, 102.0, 4.0),
    ]
    assert depth.filter(pl.col("time_exchange") == BASE + timedelta(seconds=2)).select(
        "side", "level", "price", "size"
    ).rows() == [
        ("bid", 1, 98.0, 5.0),
        ("ask", 1, 99.0, 2.0),
    ]
    assert l1.select(
        "time_exchange",
        "best_bid_px",
        "best_bid_sx",
        "best_ask_px",
        "best_ask_sx",
    ).rows()[-1] == (BASE + timedelta(seconds=2), 98.0, 5.0, 99.0, 2.0)


def test_l4_trigger_and_non_live_orders_are_excluded_from_resting_depth() -> None:
    events = [
        _l4_event(0, "SNAPSHOT", "bid", True, 100.0, 2.0),
        _l4_event(0, "SNAPSHOT", "ask", False, 101.0, 3.0),
        _l4_event(
            0,
            "SNAPSHOT",
            "stop",
            True,
            110.0,
            50.0,
            is_trigger=True,
            order_type="Stop Market",
        ),
        _l4_event(
            1,
            "SET",
            "rejected",
            True,
            109.0,
            40.0,
            hl4_status="REJECTED_MARGIN",
        ),
    ]

    depth = reconstruct_l4_depth(events)

    assert depth.filter(pl.col("time_exchange") == BASE).select(
        "side", "level", "price", "size"
    ).rows() == [("bid", 1, 100.0, 2.0), ("ask", 1, 101.0, 3.0)]
    assert depth.filter(pl.col("time_exchange") == BASE + timedelta(seconds=1)).select(
        "side", "level", "price", "size"
    ).rows() == [("bid", 1, 100.0, 2.0), ("ask", 1, 101.0, 3.0)]


def test_l4_schema_eras_use_every_available_live_order_field() -> None:
    legacy_columns = (
        "time_exchange",
        "update_type",
        "is_buy",
        "entry_px",
        "entry_sx",
        "order_id",
    )
    legacy_event = _l4_event(0, "SNAPSHOT", "bid", True, 100.0, 2.0)
    for optional in ("is_trigger", "order_type", "hl4_status"):
        legacy_event.pop(optional)

    assert _book_columns_for_schema(legacy_columns) == legacy_columns
    assert reconstruct_l4_depth([legacy_event]).select("price", "size").rows() == [
        (100.0, 2.0)
    ]


def test_off_book_trigger_does_not_change_depth_consumed_metrics() -> None:
    events, l1, _ = _cascade_fixture()
    book_events = [
        _l4_event(-1, "SNAPSHOT", "bid-1", True, 99.0, 2.0),
        _l4_event(-1, "SNAPSHOT", "bid-2", True, 98.0, 3.0),
        _l4_event(-1, "SNAPSHOT", "bid-3", True, 97.0, 4.0),
        _l4_event(-1, "SNAPSHOT", "ask", False, 101.0, 5.0),
        _l4_event(
            -1,
            "SNAPSHOT",
            "stop",
            True,
            110.0,
            50.0,
            is_trigger=True,
            order_type="Stop Market",
        ),
    ]
    depth = reconstruct_l4_depth(book_events)

    anatomy = compute_cascade_anatomy(events, l1, depth)

    row = anatomy.row(0, named=True)
    assert row["depth_levels_consumed"] == 3
    assert row["depth_size_consumed"] == pytest.approx(6.0)


def test_pair_with_one_crossed_leg_is_excluded_from_both_markout_sides() -> None:
    fills = pl.DataFrame(
        {
            "pair_id": ["matched", "matched", "one-crossed-leg"],
            "window_type": ["forced-flow", "baseline", "forced-flow"],
            "net_markout_30s_bps": [1.0, 2.0, 99.0],
        }
    )

    matched = _matched_pair_fills(fills)

    assert matched.select("pair_id", "window_type").rows() == [
        ("matched", "forced-flow"),
        ("matched", "baseline"),
    ]


def test_quote_coverage_metadata_reports_era_and_differential_attenuation() -> None:
    coverage = pl.DataFrame(
        {
            "window_start": [
                datetime(2026, 6, 1),
                datetime(2026, 6, 2),
                datetime(2026, 6, 20),
                datetime(2026, 6, 1),
                datetime(2026, 6, 2),
                datetime(2026, 6, 3),
            ],
            "window_type": ["forced-flow"] * 3 + ["baseline"] * 3,
            "quote_rows": [100] * 6,
            "crossed_quote_rows": [0, 50, 100, 0, 10, 20],
            "crossed_row_fraction": [0.0, 0.5, 1.0, 0.0, 0.1, 0.2],
            "usable_quote_rows": [100, 50, 0, 100, 90, 80],
            "dropped_for_crossed_quotes": [False, False, True, False, False, False],
        }
    )

    summary = _quote_coverage_summary(coverage)

    assert summary["first_usable_quote_date"] == "2026-06-01"
    assert summary["last_usable_quote_date"] == "2026-06-03"
    assert summary["window_count"] == 6
    assert summary["crossed_quote_dropped_window_count"] == 1
    assert summary["crossed_quote_dropped_window_fraction"] == pytest.approx(1 / 6)
    assert summary["forced_flow_mean_crossed_row_fraction"] == pytest.approx(0.5)
    assert summary["baseline_mean_crossed_row_fraction"] == pytest.approx(0.1)
    assert summary[
        "forced_flow_minus_baseline_mean_crossed_row_fraction"
    ] == pytest.approx(0.4)


def _quote(seconds: float, microprice: float) -> dict[str, object]:
    return {
        "time_exchange": BASE + timedelta(seconds=seconds),
        "best_bid_px": microprice - 1.0,
        "best_bid_sx": 1.0,
        "best_ask_px": microprice + 1.0,
        "best_ask_sx": 1.0,
    }


def _cascade_fixture() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    event = pl.DataFrame(
        [
            {
                "event_id": "SKHX-1",
                "market": "SKHX",
                "start_time": BASE,
                "end_time": BASE + timedelta(seconds=10),
                "direction": "SELL",
                "aggressor_size": 6.0,
                "tag_label": "proxy-tagged",
            }
        ]
    )
    l1 = pl.DataFrame(
        [
            _quote(-60, 100.0),
            _quote(-30, 100.0),
            _quote(-1, 100.0),
            _quote(0, 99.0),
            _quote(2, 96.0),
            _quote(4, 97.0),
            _quote(6, 98.0),
            _quote(10, 99.0),
        ]
    )
    depth = pl.DataFrame(
        [
            {"time_exchange": BASE - timedelta(seconds=1), "side": "bid", "level": 1, "price": 99.0, "size": 2.0},
            {"time_exchange": BASE - timedelta(seconds=1), "side": "bid", "level": 2, "price": 98.0, "size": 3.0},
            {"time_exchange": BASE - timedelta(seconds=1), "side": "bid", "level": 3, "price": 97.0, "size": 4.0},
            {"time_exchange": BASE - timedelta(seconds=1), "side": "ask", "level": 1, "price": 101.0, "size": 5.0},
        ]
    )
    return event, l1, depth


def test_cascade_anatomy_fixture_matches_paper_metrics() -> None:
    events, l1, depth = _cascade_fixture()

    anatomy = compute_cascade_anatomy(events, l1, depth)

    row = anatomy.row(0, named=True)
    assert row["tag_label"] == "proxy-tagged"
    assert row["pre_event_microprice_mean"] == pytest.approx(100.0)
    assert row["overshoot_price"] == pytest.approx(4.0)
    assert row["overshoot_bps"] == pytest.approx(400.0)
    assert row["overshoot_time"] == BASE + timedelta(seconds=2)
    assert row["reversion_half_life_seconds"] == pytest.approx(4.0)
    assert row["duration_seconds"] == pytest.approx(10.0)
    assert row["depth_levels_consumed"] == 3
    assert row["depth_size_consumed"] == pytest.approx(6.0)
    assert row["depth_size_available"] == pytest.approx(9.0)
    assert row["depth_size_shortfall"] == pytest.approx(0.0)


def test_reversion_half_life_never_retraces_is_null_and_counted_as_censored() -> None:
    events, l1, depth = _cascade_fixture()
    never_retraces = l1.filter(pl.col("time_exchange") <= BASE + timedelta(seconds=4))

    anatomy = compute_cascade_anatomy(events, never_retraces, depth)

    row = anatomy.row(0, named=True)
    assert row["reversion_half_life_seconds"] is None
    assert row["reversion_censored"] is True
    assert anatomy["reversion_censored"].sum() == 1


def test_zero_adverse_overshoot_has_null_half_life_and_is_counted() -> None:
    events, l1, depth = _cascade_fixture()
    no_adverse_move = l1.with_columns(
        pl.when(pl.col("time_exchange") >= BASE)
        .then(pl.lit(101.0))
        .otherwise(pl.col("best_bid_px") + 1.0)
        .alias("best_bid_px"),
        pl.when(pl.col("time_exchange") >= BASE)
        .then(pl.lit(103.0))
        .otherwise(pl.col("best_ask_px") - 1.0)
        .alias("best_ask_px"),
    )

    anatomy = compute_cascade_anatomy(events, no_adverse_move, depth)

    row = anatomy.row(0, named=True)
    assert row["overshoot_price"] == pytest.approx(0.0)
    assert row["reversion_half_life_seconds"] is None
    assert row["zero_overshoot"] is True
    assert anatomy["zero_overshoot"].sum() == 1


def test_anatomy_pre_event_baseline_is_ground_truth_and_post_event_independent() -> None:
    events, l1, depth = _cascade_fixture()
    changed = l1.with_columns(
        pl.when(pl.col("time_exchange") >= BASE)
        .then(pl.col("best_bid_px") + 10_000.0)
        .otherwise(pl.col("best_bid_px"))
        .alias("best_bid_px"),
        pl.when(pl.col("time_exchange") >= BASE)
        .then(pl.col("best_ask_px") + 10_000.0)
        .otherwise(pl.col("best_ask_px"))
        .alias("best_ask_px"),
    )

    baseline = compute_cascade_anatomy(events, l1, depth).row(0, named=True)
    altered = compute_cascade_anatomy(events, changed, depth).row(0, named=True)

    # This is pinned independently to the paper value, rather than merely
    # comparing two executions of the same implementation.
    assert baseline["pre_event_microprice_mean"] == pytest.approx(100.0)
    assert altered["pre_event_microprice_mean"] == pytest.approx(100.0)
    assert baseline["pre_event_observation_count"] == 3
    assert altered["pre_event_observation_count"] == 3


def test_over_budget_pull_is_downscoped_by_strength_without_silent_cap() -> None:
    pairs = [
        PullWindowPair(
            pair_id="weak",
            market="SKHX",
            event=Window(BASE, BASE + timedelta(hours=1)),
            baseline=Window(BASE - timedelta(days=1), BASE - timedelta(days=1) + timedelta(hours=1)),
            burst_strength=10.0,
            object_keys=("weak-event", "weak-baseline"),
        ),
        PullWindowPair(
            pair_id="strong",
            market="SMSN",
            event=Window(BASE, BASE + timedelta(hours=1)),
            baseline=Window(BASE - timedelta(days=2), BASE - timedelta(days=2) + timedelta(hours=1)),
            burst_strength=100.0,
            object_keys=("strong-event", "strong-baseline"),
        ),
        PullWindowPair(
            pair_id="middle",
            market="SKHX",
            event=Window(BASE, BASE + timedelta(hours=1)),
            baseline=Window(BASE - timedelta(days=3), BASE - timedelta(days=3) + timedelta(hours=1)),
            burst_strength=50.0,
            object_keys=("middle-event", "middle-baseline"),
        ),
    ]
    costs = {
        "weak-event": 8.0,
        "weak-baseline": 8.0,
        "middle-event": 8.0,
        "middle-baseline": 8.0,
        "strong-event": 8.0,
        "strong-baseline": 8.0,
    }

    selection = select_window_pairs_within_budget(
        pairs,
        cost_for_keys=lambda keys: sum(costs[key] for key in set(keys)),
        budget_usd=40.0,
    )

    assert selection.original_cost_usd == pytest.approx(48.0)
    assert selection.selected_cost_usd == pytest.approx(32.0)
    assert [pair.pair_id for pair in selection.selected_pairs] == ["strong", "middle"]
    assert [pair.pair_id for pair in selection.dropped_pairs] == ["weak"]
    assert selection.downscoped is True
    assert selection.coverage_cut_reason == "T7 pull estimate exceeded $40.00"


def test_budget_skip_keeps_later_pair_with_zero_marginal_shared_objects() -> None:
    pairs = [
        PullWindowPair(
            pair_id="selected-first",
            market="SKHX",
            event=Window(BASE, BASE + timedelta(hours=1)),
            baseline=None,
            burst_strength=100.0,
            object_keys=("shared-hour",),
        ),
        PullWindowPair(
            pair_id="over-budget",
            market="SMSN",
            event=Window(BASE, BASE + timedelta(hours=1)),
            baseline=None,
            burst_strength=50.0,
            object_keys=("expensive-hour",),
        ),
        PullWindowPair(
            pair_id="zero-marginal",
            market="SKHX",
            event=Window(BASE + timedelta(minutes=10), BASE + timedelta(hours=1)),
            baseline=None,
            burst_strength=10.0,
            object_keys=("shared-hour",),
        ),
    ]
    costs = {"shared-hour": 4.0, "expensive-hour": 10.0}

    selection = select_window_pairs_within_budget(
        pairs,
        cost_for_keys=lambda keys: sum(costs[key] for key in set(keys)),
        budget_usd=5.0,
    )

    assert [pair.pair_id for pair in selection.selected_pairs] == [
        "selected-first",
        "zero-marginal",
    ]
    assert [pair.pair_id for pair in selection.dropped_pairs] == ["over-budget"]
    assert selection.selected_cost_usd == pytest.approx(4.0)
