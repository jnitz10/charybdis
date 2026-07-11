import math
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from charybdis.study3_census import (
    APR_FACTOR,
    LIQUIDITY_FLOOR_USD,
    add_mean_apr_bootstrap_cis,
    build_capacity_map,
    build_census,
    build_frozen_universe,
    compute_market_stats,
    compute_weekly_rank_persistence,
    estimate_ar1_half_life,
    spearman_rank_correlation,
)


def test_ar1_half_life_recovers_known_phi() -> None:
    phi = 0.8
    values = [2.0]
    for _ in range(200):
        values.append(1.25 + phi * (values[-1] - 1.25))

    estimate = estimate_ar1_half_life(values)

    assert estimate.phi == pytest.approx(phi, abs=1e-10)
    assert estimate.half_life_hours == pytest.approx(
        math.log(0.5) / math.log(phi), abs=1e-9
    )


def test_persistence_estimators_exclude_pairs_that_cross_an_interior_gap() -> None:
    times = [datetime(2026, 1, 1) + timedelta(hours=i) for i in range(50)]
    times = [timestamp if i < 25 else timestamp + timedelta(hours=1) for i, timestamp in enumerate(times)]
    frame = pl.DataFrame(
        {
            "market": ["dex:GAP"] * len(times),
            "time_exchange": times,
            "funding_rate": [math.cos(2 * math.pi * i / 6) for i in range(50)],
        }
    )

    stats = compute_market_stats(frame).row(0, named=True)

    assert stats["ar1_pair_count"] == 48
    assert stats["ac1_pair_count"] == 48
    assert stats["ac24_pair_count"] == 2


def test_hand_computable_stats_runs_and_rank_correlation() -> None:
    apr_values = [-0.10, 0.30, 1.20, 3.50, 0.20, 1.10]
    frame = pl.DataFrame(
        {
            "market": ["dex:A"] * len(apr_values),
            "time_exchange": pl.datetime_range(
                start=pl.datetime(2026, 1, 1),
                end=pl.datetime(2026, 1, 1, 5),
                interval="1h",
                eager=True,
            ),
            "funding_rate": [value / APR_FACTOR for value in apr_values],
        }
    )

    stats = compute_market_stats(frame).row(0, named=True)

    assert stats["pct_positive_hours"] == pytest.approx(5 / 6)
    assert stats["regime_25_count"] == 2
    assert stats["regime_25_mean_hours"] == pytest.approx(2.0)
    assert stats["regime_25_median_hours"] == pytest.approx(2.0)
    assert stats["regime_100_count"] == 2
    assert stats["regime_100_mean_hours"] == pytest.approx(1.5)
    assert stats["regime_100_median_hours"] == pytest.approx(1.5)
    assert stats["regime_300_count"] == 1
    assert stats["regime_300_mean_hours"] == pytest.approx(1.0)
    assert stats["regime_300_median_hours"] == pytest.approx(1.0)
    assert spearman_rank_correlation([1, 2, 3], [3, 1, 2]) == pytest.approx(-0.5)


def test_coverage_excludes_no_data_but_includes_candle_truncated() -> None:
    funding = pl.DataFrame(
        {
            "market": ["dex:GOOD", "dex:CANDLES", "dex:NONE"],
            "time_exchange": [datetime(2026, 1, 1)] * 3,
            "funding_rate": [0.001, 0.002, 0.999],
        },
        schema_overrides={"time_exchange": pl.Datetime("us")},
    )
    coverage = {
        "dex:GOOD": "complete",
        "dex:CANDLES": "candle_truncated",
        "dex:NONE": "no_data",
    }

    census = build_census(funding, coverage)

    assert set(census["market"]) == {"dex:GOOD", "dex:CANDLES"}
    assert census.filter(pl.col("market") == "dex:CANDLES").height == 1
    assert census.filter(pl.col("market") == "dex:NONE").is_empty()


def test_weekly_cross_sectional_rank_persistence_is_market_specific() -> None:
    weekly_ranks = {
        "dex:A": [1.0, 2.0, 3.0, 2.0],
        "dex:B": [2.0, 3.0, 1.0, 1.0],
        "dex:C": [3.0, 1.0, 2.0, 3.0],
    }
    rows = []
    for week in range(4):
        for market, ranks in weekly_ranks.items():
            rows.append(
                {
                    "market": market,
                    "time_exchange": datetime(2026, 1, 5 + 7 * week),
                    "funding_rate": ranks[week] / APR_FACTOR,
                }
            )

    persistence = compute_weekly_rank_persistence(pl.DataFrame(rows))
    market_a = persistence.filter(pl.col("market") == "dex:A").row(0, named=True)

    assert market_a["weekly_rank_observations"] == 4
    assert market_a["week_over_week_rank_corr"] == pytest.approx(0.0, abs=1e-12)


def test_carry_evidence_distinguishes_insufficient_from_measured_failure() -> None:
    weekly_ranks = {
        "dex:A": [1.0, 2.0, 3.0, 2.0],
        "dex:B": [2.0, 3.0, 1.0, 1.0],
        "dex:C": [3.0, 1.0, 2.0, 3.0],
    }
    start = datetime(2026, 1, 5)
    rows = []
    for hour in range(4 * 7 * 24):
        week = hour // (7 * 24)
        for phase, (market, ranks) in enumerate(weekly_ranks.items()):
            rows.append(
                {
                    "market": market,
                    "time_exchange": start + timedelta(hours=hour),
                    "funding_rate": (
                        ranks[week] * 1e-8
                        + 1e-4 * math.cos(2 * math.pi * (hour + phase) / 6)
                    ),
                }
            )
    one_week_rows = [
        row
        for row in rows
        if row["market"] == "dex:A"
        and row["time_exchange"] < start + timedelta(weeks=1)
    ]

    one_week = build_census(
        pl.DataFrame(one_week_rows), {"dex:A": "complete"}
    ).row(0, named=True)
    measured = build_census(
        pl.DataFrame(rows), {market: "complete" for market in weekly_ranks}
    ).filter(pl.col("market") == "dex:A").row(0, named=True)

    assert one_week["week_over_week_rank_corr"] is None
    assert one_week["carry_evidence"] == "insufficient"
    assert not one_week["carry_relevant"]
    assert measured["week_over_week_rank_corr"] is not None
    assert measured["shock_half_life_hours"] is not None
    assert measured["shock_half_life_hours"] < 24.0
    assert measured["carry_evidence"] == "measured_fail"
    assert not measured["carry_relevant"]


def test_three_week_rank_series_is_insufficient_evidence() -> None:
    weekly_ranks = {
        "dex:A": [1.0, 2.0, 3.0],
        "dex:B": [2.0, 3.0, 1.0],
        "dex:C": [3.0, 1.0, 2.0],
    }
    start = datetime(2026, 1, 5)
    rows = []
    for hour in range(3 * 7 * 24):
        week = hour // (7 * 24)
        for phase, (market, ranks) in enumerate(weekly_ranks.items()):
            rows.append(
                {
                    "market": market,
                    "time_exchange": start + timedelta(hours=hour),
                    "funding_rate": (
                        ranks[week] * 1e-8
                        + 1e-4 * math.cos(2 * math.pi * (hour + phase) / 6)
                    ),
                }
            )

    row = build_census(
        pl.DataFrame(rows), {market: "complete" for market in weekly_ranks}
    ).filter(pl.col("market") == "dex:A").row(0, named=True)

    assert row["weekly_rank_observations"] == 3
    assert row["week_over_week_rank_corr"] is None
    assert row["carry_evidence"] == "insufficient"
    assert not row["carry_relevant"]


def test_capacity_products_and_frozen_universe_schema() -> None:
    census = pl.DataFrame(
        {
            "market": ["dex:A"],
            "coverage_status": ["candle_truncated"],
            "mean_apr": [0.50],
            "carry_relevant": [True],
            "carry_evidence": ["carry"],
        }
    )
    snapshots = pl.DataFrame(
        {
            "market": ["dex:A"],
            "openInterest": [2_000.0],
            "oraclePx": [10.0],
            "dayNtlVlm": [1_000_001.0],
        }
    )

    capacity = build_capacity_map(census, snapshots).row(0, named=True)
    universe = build_frozen_universe(census, snapshots)

    assert capacity["open_interest_notional_usd"] == pytest.approx(20_000.0)
    assert capacity["mean_apr_x_open_interest_notional_usd"] == pytest.approx(10_000.0)
    assert capacity["mean_apr_x_day_ntl_vlm_usd"] == pytest.approx(500_000.5)
    assert universe.columns == [
        "market",
        "coverage_status",
        "passes_liquidity_floor",
        "liquidity_floor_usd",
        "carry_relevant",
        "carry_evidence",
        "mean_apr",
        "open_interest_base",
        "open_interest_notional_usd",
        "day_ntl_vlm_usd",
    ]
    assert universe["passes_liquidity_floor"].item()
    assert universe["liquidity_floor_usd"].item() == LIQUIDITY_FLOOR_USD


def test_mean_apr_ci_reuses_six_hour_cluster_bootstrap() -> None:
    funding = pl.DataFrame(
        {
            "market": ["dex:A"] * 30,
            "time_exchange": [datetime(2026, 1, 1) + i * timedelta(hours=1) for i in range(30)],
            "funding_rate": [(i % 3) / APR_FACTOR for i in range(30)],
        }
    )
    census = build_census(funding, {"dex:A": "complete"})

    result = add_mean_apr_bootstrap_cis(census, funding).row(0, named=True)

    assert result["mean_apr_bootstrap_n"] == 30
    assert result["mean_apr_bootstrap_G"] == 5
    assert not result["mean_apr_ci_insufficient_clusters"]
    assert result["mean_apr_ci_low"] <= result["mean_apr"] <= result["mean_apr_ci_high"]


def test_report_discloses_structural_gate_and_t3_selection_contract() -> None:
    root = Path(__file__).parents[1]
    report = (root / "docs/reports/study3_funding_census_2026-07-10.md").read_text()
    census = pl.read_parquet(root / "data/reports/study3_sa_census.parquet")
    counts = census.group_by("carry_evidence").len()
    count_by_state = dict(counts.select("carry_evidence", "len").iter_rows())

    assert "STRUCTURALLY UNREACHABLE at hourly funding cadence" in report
    assert "24-hour half-life requires phi ≥ 0.9715" in report
    assert "maximum observed phi is 0.933" in report
    assert "operator override point" in report.lower()
    assert "not \"carry is dead\"" in report.lower()
    assert "Shock-half-life distribution" in report
    assert (
        "carry / measured_fail / insufficient: "
        f"{count_by_state.get('carry', 0)} / "
        f"{count_by_state.get('measured_fail', 0)} / "
        f"{count_by_state.get('insufficient', 0)}"
    ) in report
    assert (
        "S-C (T3) selects its universe by the USD 1,000,000 liquidity floor plus "
        "coverage, not by `carry_relevant`"
    ) in report
