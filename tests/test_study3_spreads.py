import math
import inspect
from datetime import datetime, timedelta

import polars as pl
import pytest


def _fees(maker_a: float = 1.0, maker_b: float = 2.0, taker_a: float = 4.0, taker_b: float = 5.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "dex": ["alpha", "beta"],
            "effective_maker_bps": [maker_a, maker_b],
            "effective_taker_bps": [taker_a, taker_b],
        }
    )


def test_breakeven_arithmetic_and_amortization_are_exact() -> None:
    from charybdis.study3_spreads import amortized_breakeven_apr, round_trip_cost_bps

    # Two transactions per leg. Maker rests, so 2 * (1 + 2) = 6 bps.
    # Taker: 2 * [(4 + 0.5) + (5 + 1.5)] = 22 bps.
    costs = round_trip_cost_bps(
        "alpha:SAME",
        "beta:SAME",
        fee_table=_fees(),
        half_spread_bps={"alpha:SAME": 0.5, "beta:SAME": 1.5},
    )

    assert costs.maker_bps == 6.0
    assert costs.taker_bps == 22.0
    assert amortized_breakeven_apr(costs.maker_bps, 24.0) == pytest.approx(0.219)
    assert amortized_breakeven_apr(costs.taker_bps, 24.0) == 0.803


def test_twin_alignment_uses_underlier_not_ticker_similarity() -> None:
    from charybdis.study3_spreads import align_twin_pairs

    markets = ["xyz:SP500", "km:US500", "flx:USA500", "other:SP500X"]
    pairs = align_twin_pairs(markets)
    aligned = {(pair.market_a, pair.market_b, pair.underlier) for pair in pairs}

    assert ("km:US500", "xyz:SP500", "SP500") in aligned
    assert ("flx:USA500", "xyz:SP500", "SP500") in aligned
    assert not any("other:SP500X" in pair[:2] for pair in aligned)


def test_persistence_half_life_recovers_exponential_decay() -> None:
    from charybdis.study3_spreads import persistence_half_life_hours

    expected = 12.0
    phi = math.exp(math.log(0.5) / expected)
    values = [3.0 * phi**hour for hour in range(240)]
    times = [datetime(2026, 1, 1) + timedelta(hours=hour) for hour in range(len(values))]

    assert persistence_half_life_hours(values, times) == pytest.approx(expected, abs=1e-8)


def test_fee_costs_are_single_sourced_from_fee_table() -> None:
    from charybdis.study3_spreads import round_trip_cost_bps

    spreads = {"alpha:SAME": 0.5, "beta:SAME": 1.5}
    baseline = round_trip_cost_bps(
        "alpha:SAME", "beta:SAME", fee_table=_fees(), half_spread_bps=spreads
    )
    changed = round_trip_cost_bps(
        "alpha:SAME",
        "beta:SAME",
        fee_table=_fees(maker_a=7.0, maker_b=11.0, taker_a=13.0, taker_b=17.0),
        half_spread_bps=spreads,
    )

    assert changed.maker_bps - baseline.maker_bps == 2.0 * ((7.0 + 11.0) - (1.0 + 2.0))
    assert changed.taker_bps - baseline.taker_bps == 2.0 * ((13.0 + 17.0) - (4.0 + 5.0))


def test_basis_metrics_are_invariant_to_constant_rescaling_of_either_leg() -> None:
    """Changing quote units must not change twin-basis risk."""

    from charybdis.run_study3_spreads import _basis_frame
    from charybdis.study3_spreads import TwinPair

    start = datetime(2026, 1, 1)
    times = [start + timedelta(hours=hour) for hour in range(6)]
    left_prices = [100.0, 101.0, 99.0, 103.0, 102.0, 104.0]
    right_prices = [50.0, 50.4, 49.7, 51.2, 50.8, 51.9]
    pair = TwinPair("SAME", "alpha:SAME", "beta:SAME")

    def metrics(left_scale: float, right_scale: float) -> tuple[float, float]:
        groups = {
            pair.market_a: pl.DataFrame(
                {"time": times, "close": [left_scale * value for value in left_prices]}
            ),
            pair.market_b: pl.DataFrame(
                {"time": times, "close": [right_scale * value for value in right_prices]}
            ),
        }
        basis = _basis_frame(pair, groups)
        return (
            float(basis["basis"].std(ddof=1)),
            float(basis["abs_basis"].quantile(0.95, interpolation="linear")),
        )

    baseline = metrics(1.0, 1.0)
    assert metrics(46.0, 1.0) == pytest.approx(baseline, abs=1e-12)
    assert metrics(1.0, 0.1) == pytest.approx(baseline, abs=1e-12)


def test_analyze_pairs_marks_differential_that_never_exceeds_breakeven(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from charybdis.markout import BootstrapCI
    import charybdis.run_study3_spreads as runner

    def point_only(frame: pl.DataFrame, statistic: object) -> BootstrapCI:
        point = statistic(frame)  # type: ignore[operator]
        return BootstrapCI(point, point, point, frame.height, 6, False)

    monkeypatch.setattr(runner, "_bootstrap", point_only)
    start = datetime(2026, 1, 1)
    times = [start + timedelta(hours=hour) for hour in range(12)]
    abs_diff_apr = [0.01 + 0.005 * 0.5**hour for hour in range(12)]
    universe = pl.DataFrame(
        {"market": ["alpha:SAME", "beta:SAME"], "coverage_status": ["ok", "ok"]}
    )
    funding = pl.DataFrame(
        {
            "market": ["alpha:SAME"] * 12 + ["beta:SAME"] * 12,
            "time_exchange": times + times,
            "funding_rate": [value / (24.0 * 365.0) for value in abs_diff_apr]
            + [0.0] * 12,
        }
    )
    candles = pl.DataFrame(
        {
            "market": ["alpha:SAME"] * 12 + ["beta:SAME"] * 12,
            "time_open": times + times,
            "close": [100.0 + hour for hour in range(12)] * 2,
        }
    )
    spreads = pl.DataFrame(
        {
            "market": ["alpha:SAME", "beta:SAME"],
            "half_spread_bps": [0.5, 0.5],
            "half_spread_source": ["test", "test"],
        }
    )

    row = runner.analyze_pairs(universe, funding, candles, _fees(), spreads).row(
        0, named=True
    )

    assert row["maker_n_episodes"] == 0
    assert row["taker_n_episodes"] == 0
    assert row["maker_never_exceeds_breakeven"] is True
    assert row["taker_never_exceeds_breakeven"] is True
    assert math.isnan(row["maker_median_episode_hours"])
    assert math.isnan(row["taker_median_episode_hours"])


def test_report_attributes_fe_failure_to_corrected_basis_and_primary_kill_leg() -> None:
    from charybdis.run_study3_spreads import render_report

    results = pl.read_parquet("data/reports/study3_se_spreads.parquet")
    report = render_report(results)

    assert "All 57 pairs remain F-E dead" in report
    assert "basis/twin-basis risk swamps the funding differential" in report
    assert "never-reaches-breakeven" in report
    assert "primary maker kill leg" in report
    assert "40/57 pairs never reach taker breakeven" in report
    assert "Most pairs never even reach maker breakeven" not in report
    assert "deployer oracle/index construction" not in report
    numeric_section = report.split("## F-E numeric quantities (no verdicts)", 1)[1].split(
        "## Cost and coverage caveats", 1
    )[0]
    assert "dead" not in numeric_section.lower()
    assert "kill" not in numeric_section.lower()


def test_report_flags_sub_hour_top_differentials_as_venue_quality_artifacts() -> None:
    from charybdis.run_study3_spreads import render_report

    report = render_report(pl.read_parquet("data/reports/study3_se_spreads.parquet"))

    assert "flx:XMR|hyna:XMR" in report
    assert "near-dead `hyna` venue" in report
    assert "venue-quality/erratic-funding artifact, not an opportunity" in report
    assert "4.44% maker and 1.39% taker" in report
    assert "Sub-1h top-differential artifacts" in report


def test_spread_pipeline_has_one_source_of_truth_for_half_life_and_episode_median() -> None:
    import charybdis.run_study3_spreads as runner
    import charybdis.study3_spreads as spreads

    assert not hasattr(spreads, "persistence_half_life_frame")
    source = inspect.getsource(runner.analyze_pairs)
    assert source.count("median_episode_duration(") == 2
