from __future__ import annotations

from datetime import datetime, timedelta
import random

import polars as pl
import pytest

from charybdis.markout import (
    DEFAULT_MAKER_FEE_ASSUMED,
    DEFAULT_MAKER_FEE_BPS,
    HORIZONS_SECONDS,
    build_fill_markouts,
    cluster_bootstrap_ci,
    microprice_frame,
    primary_summary,
    secondary_summary,
    write_fill_records,
)


BASE = datetime(2026, 7, 6, 14, 0, 0)  # naive UTC; 10:00 NYSE local


def _frame(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("time_exchange").cast(pl.Datetime("ns"))
    )


@pytest.fixture
def paper_fixture() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    # Exactly 20 L1 ticks.  The post-fill microprices for the first bid fill are
    # 101.5, 100.5, 102, 100, and 105 at 1/5/30/120/600 seconds.
    ticks = [
        (0, 100.0, 5.0, 102.0, 10.0),
        (1, 99.0, 5.0, 103.0, 3.0),
        (5, 99.0, 3.0, 103.0, 5.0),
        (10, 99.0, 4.0, 103.0, 4.0),
        (20, 100.0, 4.0, 102.0, 4.0),
        (30, 101.0, 10.0, 103.0, 10.0),
        (40, 100.0, 8.0, 104.0, 8.0),
        (50, 100.0, 8.0, None, None),  # must be skipped, never zero-filled
        (60, 98.0, 6.0, 102.0, 6.0),
        (90, 98.0, 7.0, 102.0, 7.0),
        (120, 99.0, 9.0, 101.0, 9.0),
        (180, 99.0, 8.0, 101.0, 8.0),
        (240, 100.0, 7.0, 102.0, 7.0),
        (300, 101.0, 6.0, 103.0, 6.0),
        (360, 101.0, 5.0, 103.0, 5.0),
        (420, 102.0, 4.0, 104.0, 4.0),
        (480, 102.0, 3.0, 104.0, 3.0),
        (540, 103.0, 2.0, 105.0, 2.0),
        (600, 104.0, 10.0, 106.0, 10.0),
        (700, 104.0, 9.0, 106.0, 9.0),
    ]
    l1 = _frame(
        [
            {
                "time_exchange": BASE + timedelta(seconds=second),
                "best_bid_px": bid,
                "best_bid_sx": bid_size,
                "best_ask_px": ask,
                "best_ask_sx": ask_size,
            }
            for second, bid, bid_size, ask, ask_size in ticks
        ]
    )
    trades = _frame(
        [
            # A quote is joined only after its L1 tick, so this cannot fill it.
            {"time_exchange": BASE, "price": 200.0, "base_amount": 100.0},
            {"time_exchange": BASE + timedelta(seconds=0.05), "price": 102.0, "base_amount": 4.0},
            {"time_exchange": BASE + timedelta(seconds=0.10), "price": 100.0, "base_amount": 3.0},
            {"time_exchange": BASE + timedelta(seconds=0.15), "price": 102.0, "base_amount": 6.0},
            {"time_exchange": BASE + timedelta(seconds=0.20), "price": 100.0, "base_amount": 2.0},
            {"time_exchange": BASE + timedelta(seconds=0.25), "price": 102.0, "base_amount": 0.1},
            {"time_exchange": BASE + timedelta(seconds=0.30), "price": 100.0, "base_amount": 0.1},
            # Strictly-through prints fill immediately at the newly joined touch.
            {"time_exchange": BASE + timedelta(seconds=1.10), "price": 104.0, "base_amount": 0.2},
            {"time_exchange": BASE + timedelta(seconds=1.20), "price": 98.0, "base_amount": 0.2},
        ]
    )
    funding = _frame(
        [
            {
                "time_exchange": BASE - timedelta(hours=1),
                "market": "xyz:SP500",
                "hourly_rate": 0.0036,
            }
        ]
    )
    return l1, trades, funding


def test_hand_built_20_tick_fills_microprice_and_money_math(
    paper_fixture: tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame],
) -> None:
    l1, trades, funding = paper_fixture
    fills = build_fill_markouts(l1, trades, market="xyz:SP500", funding=funding)

    assert DEFAULT_MAKER_FEE_BPS == 1.5
    assert DEFAULT_MAKER_FEE_ASSUMED is True
    assert fills.select("side", "fill_price", "fill_time").rows() == [
        ("sell", 102.0, BASE + timedelta(seconds=0.25)),
        ("buy", 100.0, BASE + timedelta(seconds=0.30)),
        ("sell", 103.0, BASE + timedelta(seconds=1.10)),
        ("buy", 99.0, BASE + timedelta(seconds=1.20)),
    ]

    buy = fills.filter(pl.col("fill_time") == BASE + timedelta(seconds=0.30)).row(
        0, named=True
    )
    expected_microprices = {
        "1s": 101.5,
        "5s": 100.5,
        "30s": 102.0,
        "2m": 100.0,
        "10m": 105.0,
    }
    expected_gross = {"1s": 150.0, "5s": 50.0, "30s": 200.0, "2m": 0.0, "10m": 500.0}
    expected_funding = {"1s": 0.01, "5s": 0.05, "30s": 0.30, "2m": 1.20, "10m": 6.00}
    for label in HORIZONS_SECONDS:
        assert buy[f"microprice_{label}"] == pytest.approx(expected_microprices[label])
        assert buy[f"gross_markout_{label}_bps"] == pytest.approx(expected_gross[label])
        assert buy[f"funding_drift_{label}_bps"] == pytest.approx(expected_funding[label])
        assert buy[f"net_markout_{label}_bps"] == pytest.approx(
            expected_gross[label] - 1.5 - expected_funding[label]
        )

    assert buy["segment"] == "RTH"
    assert buy["cluster_key"] == "xyz:SP500|2026-07-06T12:00:00"
    assert buy["size_bucket"] == "trickle"
    # Positive funding benefits the short maker rather than costing it.
    sell = fills.filter(pl.col("fill_time") == BASE + timedelta(seconds=0.25)).row(
        0, named=True
    )
    assert sell["net_markout_1s_bps"] == pytest.approx(
        sell["gross_markout_1s_bps"] - 1.5 + 0.01
    )


def test_no_lookahead_future_rows_cannot_change_observed_quantities(
    paper_fixture: tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame],
) -> None:
    l1, trades, funding = paper_fixture
    baseline = build_fill_markouts(l1, trades, market="xyz:SP500", funding=funding)
    changed = l1.with_columns(
        pl.when(pl.col("time_exchange") > BASE + timedelta(seconds=10))
        .then(pl.col("best_bid_px") + 10_000.0)
        .otherwise(pl.col("best_bid_px"))
        .alias("best_bid_px"),
        pl.when(pl.col("time_exchange") > BASE + timedelta(seconds=10))
        .then(pl.col("best_ask_px") + 10_000.0)
        .otherwise(pl.col("best_ask_px"))
        .alias("best_ask_px"),
    )
    changed_result = build_fill_markouts(
        changed, trades, market="xyz:SP500", funding=funding
    )
    observed_columns = [
        "fill_time",
        "side",
        "fill_price",
        "queue_ahead",
        "microprice_1s",
        "gross_markout_1s_bps",
        "net_markout_1s_bps",
        "microprice_5s",
        "gross_markout_5s_bps",
        "net_markout_5s_bps",
    ]
    assert baseline.select(observed_columns).equals(changed_result.select(observed_columns))

    # At 5.30s, the 5.00s quote is the last observation known.  Computing that
    # markout must not require learning at 10.00s that the input file continues.
    prefix = build_fill_markouts(
        l1.filter(pl.col("time_exchange") <= BASE + timedelta(seconds=5)),
        trades.filter(pl.col("time_exchange") <= BASE + timedelta(seconds=5)),
        market="xyz:SP500",
        funding=funding,
    )
    baseline_early = baseline.filter(pl.col("fill_time") <= BASE + timedelta(seconds=0.30))
    prefix_early = prefix.filter(pl.col("fill_time") <= BASE + timedelta(seconds=0.30))
    assert baseline_early.select(observed_columns).equals(prefix_early.select(observed_columns))


def test_no_lookahead_at_30s_2m_and_10m_decision_horizons(
    paper_fixture: tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame],
) -> None:
    l1, trades, funding = paper_fixture
    baseline = build_fill_markouts(l1, trades, market="xyz:SP500", funding=funding)
    fill_time = BASE + timedelta(seconds=0.30)
    baseline_fill = baseline.filter(pl.col("fill_time") == fill_time)

    after_10m = l1.with_columns(
        pl.when(pl.col("time_exchange") > fill_time + timedelta(seconds=600))
        .then(pl.col("best_bid_px") + 10_000.0)
        .otherwise(pl.col("best_bid_px"))
        .alias("best_bid_px"),
        pl.when(pl.col("time_exchange") > fill_time + timedelta(seconds=600))
        .then(pl.col("best_ask_px") + 10_000.0)
        .otherwise(pl.col("best_ask_px"))
        .alias("best_ask_px"),
    )
    after_10m_result = build_fill_markouts(
        after_10m, trades, market="xyz:SP500", funding=funding
    ).filter(pl.col("fill_time") == fill_time)
    long_horizon_columns = [
        "microprice_30s",
        "net_markout_30s_bps",
        "microprice_2m",
        "net_markout_2m_bps",
        "microprice_10m",
        "net_markout_10m_bps",
    ]
    assert baseline_fill.select(long_horizon_columns).equals(
        after_10m_result.select(long_horizon_columns)
    )

    # The 40-second quote is strictly after this fill's 30-second target at
    # BASE+30.30, so even an extreme perturbation there cannot enter the mark.
    after_30s = l1.with_columns(
        pl.when(pl.col("time_exchange") == BASE + timedelta(seconds=40))
        .then(pl.col("best_bid_px") + 10_000.0)
        .otherwise(pl.col("best_bid_px"))
        .alias("best_bid_px"),
        pl.when(pl.col("time_exchange") == BASE + timedelta(seconds=40))
        .then(pl.col("best_ask_px") + 10_000.0)
        .otherwise(pl.col("best_ask_px"))
        .alias("best_ask_px"),
    )
    after_30s_fill = build_fill_markouts(
        after_30s, trades, market="xyz:SP500", funding=funding
    ).filter(pl.col("fill_time") == fill_time)
    assert baseline_fill["microprice_30s"].item() == pytest.approx(102.0)
    assert baseline_fill.select("microprice_30s", "net_markout_30s_bps").equals(
        after_30s_fill.select("microprice_30s", "net_markout_30s_bps")
    )


def test_one_sided_l1_is_skipped_not_zero_filled() -> None:
    l1 = _frame(
        [
            {"time_exchange": BASE, "best_bid_px": 100.0, "best_bid_sx": 2.0, "best_ask_px": 102.0, "best_ask_sx": 2.0},
            {"time_exchange": BASE + timedelta(seconds=1), "best_bid_px": 101.0, "best_bid_sx": 3.0, "best_ask_px": None, "best_ask_sx": None},
            {"time_exchange": BASE + timedelta(seconds=2), "best_bid_px": 102.0, "best_bid_sx": 1.0, "best_ask_px": 104.0, "best_ask_sx": 3.0},
        ]
    )
    microprices = microprice_frame(l1)
    assert microprices["time_exchange"].to_list() == [BASE, BASE + timedelta(seconds=2)]
    assert microprices["microprice"].to_list() == pytest.approx([101.0, 102.5])
    assert all(value > 0 for value in microprices["microprice"])


def test_stale_horizon_is_flagged_null_and_excluded_from_primary_pool() -> None:
    l1 = _frame(
        [
            {"time_exchange": BASE, "best_bid_px": 100.0, "best_bid_sx": 2.0, "best_ask_px": 102.0, "best_ask_sx": 2.0},
            {"time_exchange": BASE + timedelta(seconds=29), "best_bid_px": 100.0, "best_bid_sx": 3.0, "best_ask_px": 102.0, "best_ask_sx": 3.0},
            {"time_exchange": BASE + timedelta(seconds=100), "best_bid_px": 101.0, "best_bid_sx": 2.0, "best_ask_px": 103.0, "best_ask_sx": 2.0},
            {"time_exchange": BASE + timedelta(seconds=130), "best_bid_px": 104.0, "best_bid_sx": 2.0, "best_ask_px": 106.0, "best_ask_sx": 2.0},
        ]
    )
    trades = _frame(
        [
            {"time_exchange": BASE + timedelta(seconds=0.1), "price": 99.0, "base_amount": 1.0},
            {"time_exchange": BASE + timedelta(seconds=100.1), "price": 100.0, "base_amount": 1.0},
        ]
    )
    funding = _frame(
        [
            {
                "time_exchange": BASE - timedelta(hours=1),
                "market": "xyz:SP500",
                "hourly_rate": 0.0,
            }
        ]
    )

    fills = build_fill_markouts(
        l1,
        trades,
        market="xyz:SP500",
        funding=funding,
        max_quote_age_s=1.0,
        horizons={"30s": 30},
    ).sort("fill_time")
    stale, fresh = fills.iter_rows(named=True)

    assert stale["net_markout_30s_bps"] is None
    assert stale["stale_30s"] is True
    assert fresh["net_markout_30s_bps"] is not None
    assert fresh["stale_30s"] is False
    reference_fresh = build_fill_markouts(
        l1,
        trades,
        market="xyz:SP500",
        funding=funding,
        max_quote_age_s=60.0,
        horizons={"30s": 30},
    ).sort("fill_time").row(1, named=True)
    assert fresh["net_markout_30s_bps"] == pytest.approx(
        reference_fresh["net_markout_30s_bps"]
    )

    primary = primary_summary(fills, n_resamples=2_000, seed=4)
    assert primary["point_estimate_bps"].item() == pytest.approx(
        fresh["net_markout_30s_bps"]
    )
    assert primary["n"].item() == 1
    assert primary["staleness_rate_30s"].item() == pytest.approx(0.5)


def test_stale_entry_quote_nulls_and_flags_all_horizons() -> None:
    l1 = _frame(
        [
            {"time_exchange": BASE, "best_bid_px": 100.0, "best_bid_sx": 2.0, "best_ask_px": 102.0, "best_ask_sx": 2.0},
            {"time_exchange": BASE + timedelta(seconds=40), "best_bid_px": 101.0, "best_bid_sx": 2.0, "best_ask_px": 103.0, "best_ask_sx": 2.0},
            {"time_exchange": BASE + timedelta(seconds=130), "best_bid_px": 102.0, "best_bid_sx": 2.0, "best_ask_px": 104.0, "best_ask_sx": 2.0},
        ]
    )
    trades = _frame(
        [
            {"time_exchange": BASE + timedelta(seconds=10), "price": 99.0, "base_amount": 1.0},
        ]
    )
    funding = _frame(
        [
            {
                "time_exchange": BASE - timedelta(hours=1),
                "market": "xyz:SP500",
                "hourly_rate": 0.0,
            }
        ]
    )

    fill = build_fill_markouts(
        l1,
        trades,
        market="xyz:SP500",
        funding=funding,
        max_quote_age_s=5.0,
        horizons={"30s": 30, "2m": 120},
    ).row(0, named=True)

    for label in ("30s", "2m"):
        assert fill[f"microprice_{label}"] is None
        assert fill[f"gross_markout_{label}_bps"] is None
        assert fill[f"net_markout_{label}_bps"] is None
        assert fill[f"stale_{label}"] is True


def _percentile(sorted_values: list[float], probability: float) -> float:
    position = (len(sorted_values) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def test_cluster_bootstrap_resamples_whole_clusters_with_replacement() -> None:
    values = pl.DataFrame(
        {
            "cluster_key": ["a"] * 10 + ["b", "c"],
            "value": [0.0] * 10 + [100.0, 100.0],
        }
    )
    result = cluster_bootstrap_ci(
        values,
        value_col="value",
        n_resamples=2_000,
        seed=712,
        min_clusters=3,
    )

    clusters = [[0.0] * 10, [100.0], [100.0]]
    rng = random.Random(712)
    draws = []
    for _ in range(2_000):
        sample = [clusters[rng.randrange(3)] for _ in range(3)]
        pooled = [value for cluster in sample for value in cluster]
        draws.append(sum(pooled) / len(pooled))
    draws.sort()
    expected = (_percentile(draws, 0.025), _percentile(draws, 0.975))

    assert result.point_estimate == pytest.approx(100.0 / 6.0)
    assert (result.ci_low, result.ci_high) == pytest.approx(expected)
    assert result.ci_low <= result.point_estimate <= result.ci_high
    assert result.G == 3
    assert result.n == 12
    assert result.low_cluster is False


def test_cluster_bootstrap_ci_is_null_below_minimum_clusters() -> None:
    one_cluster = cluster_bootstrap_ci(
        pl.DataFrame({"cluster_key": ["only", "only"], "value": [1.0, 3.0]}),
        value_col="value",
        n_resamples=2_000,
        seed=1,
    )
    assert one_cluster.point_estimate == pytest.approx(2.0)
    assert one_cluster.ci_low is None
    assert one_cluster.ci_high is None
    assert one_cluster.G == 1
    assert one_cluster.low_cluster is True

    four_clusters = cluster_bootstrap_ci(
        pl.DataFrame(
            {
                "cluster_key": ["a", "b", "c", "d"],
                "value": [1.0, 2.0, 3.0, 4.0],
            }
        ),
        value_col="value",
        n_resamples=2_000,
        seed=1,
    )
    assert four_clusters.point_estimate == pytest.approx(2.5)
    assert four_clusters.ci_low is None
    assert four_clusters.ci_high is None
    assert four_clusters.G == 4
    assert four_clusters.low_cluster is True


def test_primary_secondary_summaries_and_parquet_output(
    paper_fixture: tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame], tmp_path
) -> None:
    l1, trades, funding = paper_fixture
    fills = build_fill_markouts(l1, trades, market="xyz:SP500", funding=funding)
    primary = primary_summary(fills, n_resamples=2_000, seed=4)
    secondary = secondary_summary(
        fills, by=["market", "side", "hour_of_day", "size_bucket"], n_resamples=2_000, seed=4
    )

    assert primary.columns == [
        "market", "segment", "horizon", "point_estimate_bps", "ci_low_bps",
        "ci_high_bps", "n", "G", "low_cluster", "staleness_rate_30s",
    ]
    assert primary["horizon"].unique().to_list() == ["30s"]
    assert primary["G"].to_list() == [1]
    assert primary["ci_low_bps"].to_list() == [None]
    assert primary["ci_high_bps"].to_list() == [None]
    assert primary["low_cluster"].to_list() == [True]
    assert set(secondary["side"]) == {"buy", "sell"}

    path = tmp_path / "fills.parquet"
    write_fill_records(fills, path)
    restored = pl.read_parquet(path)
    assert restored.equals(fills)
