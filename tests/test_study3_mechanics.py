from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import polars as pl
import pytest

from charybdis.study3_mechanics import (
    ENDPOINT_RESULT_LABEL,
    MAX_CONSECUTIVE_MISSING_MINUTES,
    SHUFFLE_DIAGNOSTIC_LABEL,
    clamp_regime_statistics,
    detect_cap_hits,
    funding_rate_from_premium,
    minute_r_squared_curve,
    reconcile_samples,
    regression_statistics,
    render_routing_section,
    samples_through_minute,
)


def test_endpoint_is_labeled_as_feed_reconciliation_not_predictability() -> None:
    assert ENDPOINT_RESULT_LABEL == "feed-reconciliation / formula-consistency check"


def test_reconciliation_statistics_quantify_affine_identity_gap() -> None:
    premium = np.array([-0.004, -0.001, 0.002, 0.006])
    predicted = 0.5 * premium
    realized = 0.000002 + 1.134 * predicted
    frame = pl.DataFrame(
        {
            "average_premium": premium,
            "predicted_funding": predicted,
            "realized_funding": realized,
        }
    )

    stats = regression_statistics(frame, assumed_multiplier=0.5)

    assert stats["slope"] == pytest.approx(1.134)
    assert stats["raw_premium_r_squared"] == pytest.approx(1.0)
    assert stats["mean_residual_bps"] == pytest.approx(
        np.mean(realized - predicted) * 10_000.0
    )
    assert stats["empirically_implied_multiplier"] == pytest.approx(0.567)


def test_closed_form_funding_formula_recomputes_exactly() -> None:
    premium = np.array([0.002, -0.002, 0.0001, 0.0004])
    expected = 0.5 * (
        premium + np.clip(0.0001 - premium, -0.0005, 0.0005)
    ) / 8.0

    actual = funding_rate_from_premium(
        premium,
        interest_rate=0.0001,
        funding_multiplier=0.5,
    )

    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-15)


def test_future_sample_and_shuffle_do_not_change_earlier_minute_r_squared() -> None:
    starts = pl.datetime_range(
        pl.datetime(2026, 1, 1),
        pl.datetime(2026, 1, 1, 3),
        interval="1h",
        eager=True,
    )
    premiums = [0.001, 0.002, -0.001, 0.003]
    rows = []
    for start, premium in zip(starts, premiums, strict=True):
        for minute, fraction in [(10, 0.5), (40, 1.5)]:
            rows.append(
                {
                    "market": "xyz:TEST",
                    "time_exchange": start.replace(minute=minute),
                    "update_class": "Deployer",
                    "mark_px": 100.0 * (1.0 + premium * fraction),
                    "oracle_px": 100.0,
                }
            )
    samples = pl.DataFrame(rows)
    realized = pl.DataFrame(
        {
            "market": ["xyz:TEST"] * 4,
            "time_exchange": [start.replace(hour=start.hour + 1) for start in starts],
            "funding_rate": funding_rate_from_premium(
                np.asarray(premiums), interest_rate=0.0001
            ),
        }
    )
    _, baseline = reconcile_samples(samples, realized, interest_rate=0.0001)

    # This minute-56 observation belongs to an hour with a realized settlement.
    future = pl.DataFrame(
        {
            "market": ["xyz:TEST"],
            "time_exchange": [starts[2].replace(minute=56)],
            "update_class": ["Fallback"],
            "mark_px": [1_000.0],
            "oracle_px": [100.0],
        }
    )
    shuffled = pl.concat([samples, future]).sample(fraction=1.0, shuffle=True, seed=7)
    _, injected = reconcile_samples(shuffled, realized, interest_rate=0.0001)

    left = baseline.filter(pl.col("minute") < 56).select("minute", "r_squared")
    right = injected.filter(pl.col("minute") < 56).select("minute", "r_squared")
    assert left.equals(right)
    assert samples_through_minute(future, 55).is_empty()
    assert len(samples_through_minute(future, 56)) == 1
    # Inclusion at exactly 56 makes this fail if the pipeline uses `< minute`.
    assert baseline.filter(pl.col("minute") == 56)["r_squared"][0] != injected.filter(
        pl.col("minute") == 56
    )["r_squared"][0]


def test_clamp_detection_at_exact_positive_and_negative_cap() -> None:
    # With divisor/multiplier one, the inner clamp turns +/-0.0405 into +/-0.04.
    predicted = funding_rate_from_premium(
        np.array([0.0405, -0.0405, 0.01]),
        interest_rate=0.0,
        settlement_divisor=1.0,
        hourly_cap=0.04,
    )

    np.testing.assert_array_equal(
        detect_cap_hits(predicted, hourly_cap=0.04),
        np.array([True, True, False]),
    )
    np.testing.assert_allclose(predicted[:2], [0.04, -0.04], rtol=0.0, atol=0.0)


def test_engineered_later_minutes_have_nondecreasing_r_squared() -> None:
    true_premium = np.array([-0.003, -0.001, 0.0005, 0.0015, 0.003, 0.005])
    early_noise = np.array([0.004, -0.003, 0.002, -0.004, 0.003, -0.002])
    start = pl.datetime(2026, 2, 1)
    starts = pl.datetime_range(start, start + pl.duration(hours=5), interval="1h", eager=True)
    rows = []
    for timestamp, truth, noise in zip(
        starts, true_premium, early_noise, strict=True
    ):
        for minute, premium in [(10, truth + noise), (40, truth - noise)]:
            rows.append(
                {
                    "market": "xyz:TEST",
                    "time_exchange": timestamp.replace(minute=minute),
                    "update_class": "Deployer",
                    "mark_px": 100.0 * (1.0 + premium),
                    "oracle_px": 100.0,
                }
            )
    realized = pl.DataFrame(
        {
            "market": ["xyz:TEST"] * len(starts),
            "time_exchange": [t + timedelta(hours=1) for t in starts],
            "funding_rate": true_premium,
        }
    )

    curve = minute_r_squared_curve(
        pl.DataFrame(rows),
        realized,
        interest_rate=0.0,
        clamp_bound=0.0,
        settlement_divisor=1.0,
    ).drop_nulls("r_squared")
    values = curve["r_squared"].to_numpy()

    assert values[-1] > values[0]
    assert np.all(np.diff(values) >= -1e-12)


def test_within_hour_shuffle_is_secondary_sample_timing_drift_diagnostic() -> None:
    start_time = datetime(2026, 3, 1)
    starts = [start_time + timedelta(hours=hour) for hour in range(60)]
    latent = np.linspace(-0.004, 0.004, len(starts))
    early_transient = np.random.default_rng(17).normal(0.0, 0.008, len(starts))
    rows = []
    realized_values = []
    for hour_index, start in enumerate(starts):
        premiums = []
        for minute in (0, 10, 20, 30, 40, 50, 59):
            premium = latent[hour_index] + (
                early_transient[hour_index] if minute == 0 else 0.0
            )
            premiums.append(premium)
            rows.append(
                {
                    "market": "xyz:TEST",
                    "time_exchange": start.replace(minute=minute),
                    "update_class": "Deployer",
                    "mark_px": 100.0 * (1.0 + premium),
                    "oracle_px": 100.0,
                }
            )
        realized_values.append(float(np.mean(premiums)))
    realized = pl.DataFrame(
        {
            "market": ["xyz:TEST"] * len(starts),
            "time_exchange": [t + timedelta(hours=1) for t in starts],
            "funding_rate": realized_values,
        }
    )

    curve = minute_r_squared_curve(
        pl.DataFrame(rows),
        realized,
        interest_rate=0.0,
        clamp_bound=0.0,
        settlement_divisor=1.0,
        shuffle_count=100,
        shuffle_seed=0,
    )

    assert SHUFFLE_DIAGNOSTIC_LABEL == "intra-hour sample-timing/drift diagnostic"
    assert {"observed_r2", "shuffle_r2", "shuffle_timing_gap"} <= set(curve.columns)
    minute_0 = curve.filter(pl.col("minute") == 0).row(0, named=True)
    assert minute_0["observed_r2"] < minute_0["shuffle_r2"]
    assert minute_0["shuffle_timing_gap"] == pytest.approx(
        minute_0["observed_r2"] - minute_0["shuffle_r2"]
    )
    # F-B excess is observed versus iid, never observed versus within-hour shuffle.
    assert minute_0["iid_excess"] == pytest.approx(
        minute_0["observed_r2"] - minute_0["iid_floor"]
    )


def _synthetic_iid_curve(*, stable_hour_level: bool) -> pl.DataFrame:
    """Build enough complete hours to distinguish an iid floor from persistence."""
    rng = np.random.default_rng(20260710)
    hour_count = 240
    start = datetime(2026, 6, 1)
    rows: list[dict[str, object]] = []
    realized_values: list[float] = []
    levels = rng.normal(0.0, 0.004, hour_count) if stable_hour_level else np.zeros(hour_count)
    for hour, level in enumerate(levels):
        timestamp = start + timedelta(hours=hour)
        premiums = level + rng.normal(0.0, 0.004, 60)
        realized_values.append(float(np.mean(premiums)))
        for minute, premium in enumerate(premiums):
            rows.append(
                {
                    "market": "xyz:TEST",
                    "time_exchange": timestamp.replace(minute=minute),
                    "update_class": "Deployer",
                    "mark_px": 100.0 * (1.0 + premium),
                    "oracle_px": 100.0,
                }
            )
    realized = pl.DataFrame(
        {
            "market": ["xyz:TEST"] * hour_count,
            "time_exchange": [
                start + timedelta(hours=hour + 1) for hour in range(hour_count)
            ],
            "funding_rate": realized_values,
        }
    )
    return minute_r_squared_curve(
        pl.DataFrame(rows),
        realized,
        interest_rate=0.0,
        clamp_bound=0.0,
        settlement_divisor=1.0,
        shuffle_count=100,
        shuffle_seed=0,
        iid_seed_count=100,
        iid_seed=0,
    )


def test_iid_floor_gives_near_zero_excess_for_white_noise_within_hour() -> None:
    curve = _synthetic_iid_curve(stable_hour_level=False)

    assert {"observed_r2", "iid_floor", "iid_excess"} <= set(curve.columns)
    # 240 hours leave visible finite-sample R² noise; 0.11 rejects the old ~0.99
    # floor while covering the seeded series' largest pointwise deviation (0.098).
    for minute in (0, 10, 30, 50, 59):
        row = curve.filter(pl.col("minute") == minute).row(0, named=True)
        assert row["iid_excess"] == pytest.approx(0.0, abs=0.11)


def test_iid_excess_detects_stable_hour_level_then_decays_to_zero() -> None:
    curve = _synthetic_iid_curve(stable_hour_level=True)
    minute_0 = curve.filter(pl.col("minute") == 0).row(0, named=True)
    minute_10 = curve.filter(pl.col("minute") == 10).row(0, named=True)
    minute_30 = curve.filter(pl.col("minute") == 30).row(0, named=True)
    minute_50 = curve.filter(pl.col("minute") == 50).row(0, named=True)
    minute_59 = curve.filter(pl.col("minute") == 59).row(0, named=True)

    assert minute_0["iid_excess"] > 0.35
    # The gap can rise from minute 0 while the stable level becomes estimable;
    # after that early peak it decays as the iid floor approaches full observation.
    assert minute_10["iid_excess"] > minute_30["iid_excess"] > minute_50["iid_excess"]
    assert minute_59["iid_excess"] == pytest.approx(0.0, abs=1e-12)


def test_routing_section_uses_observed_minute_50_and_three_curve_table() -> None:
    curve = pl.DataFrame(
        {
            "minute": [0, 10, 30, 50, 59],
            "observed_r2": [0.316, 0.580, 0.812, 0.962, 0.993],
            "iid_floor": [0.017, 0.183, 0.517, 0.850, 1.0],
            "iid_excess": [0.299, 0.397, 0.295, 0.112, -0.007],
            "shuffle_r2": [0.967, 0.991, 0.992, 0.993, 0.993],
        }
    )

    section = render_routing_section(curve)

    assert section.startswith(
        "## §1.6 F-B/G-F2 Routing Input — numbers only, no verdict"
    )
    assert "Pre-registered F-B metric: minute 50 observed R-squared `0.96200000`" in section
    assert "minute 10 observed R-squared `0.58000000` (50-minute lead)" in section
    assert "Minute 0 observed R-squared `0.31600000`, iid floor `0.01700000`, iid excess `0.29900000`" in section
    assert "| minute | observed_r2 | iid_floor | iid_excess | shuffle_r2 |" in section
    assert "| 30 | 0.81200000 | 0.51700000 | 0.29500000 | 0.99200000 |" in section


def test_clamp_regime_statistics_separate_constant_and_active_hours() -> None:
    frame = pl.DataFrame(
        {
            "average_premium": [0.0000, 0.0002, 0.0010, 0.0020, 0.0030],
            "predicted_funding": [0.0001, 0.0001, 0.0005, 0.0015, 0.0025],
            "realized_funding": [0.00009, 0.00011, 0.0007, 0.0017, 0.0027],
        }
    )

    split = clamp_regime_statistics(frame, interest_rate=0.0001, clamp_bound=0.0005)

    assert split["inactive"]["n"] == 2
    assert split["inactive"]["r_squared"] == pytest.approx(0.0)
    assert split["active"]["n"] == 3
    assert split["active"]["r_squared"] == pytest.approx(1.0)


def test_shuffle_timing_gap_is_zero_for_white_noise_and_positive_for_persistence() -> None:
    rng = np.random.default_rng(41)
    hour_count = 160
    start = datetime(2026, 4, 1)

    def make_curve(kind: str) -> pl.DataFrame:
        rows = []
        realized_values = []
        latent_values = np.linspace(-0.004, 0.004, hour_count)
        for hour in range(hour_count):
            timestamp = start + timedelta(hours=hour)
            if kind == "white_noise":
                premiums = rng.normal(0.0, 0.004, 60)
            else:
                transient = np.tile(np.array([0.018, -0.018]), 15)
                premiums = np.r_[
                    np.full(30, latent_values[hour]),
                    latent_values[hour] + transient,
                ]
            realized_values.append(float(np.mean(premiums)))
            for minute, premium in enumerate(premiums):
                rows.append(
                    {
                        "market": "xyz:TEST",
                        "time_exchange": timestamp.replace(minute=minute),
                        "update_class": "Deployer",
                        "mark_px": 100.0 * (1.0 + premium),
                        "oracle_px": 100.0,
                    }
                )
        realized = pl.DataFrame(
            {
                "market": ["xyz:TEST"] * hour_count,
                "time_exchange": [
                    start + timedelta(hours=hour + 1) for hour in range(hour_count)
                ],
                "funding_rate": realized_values,
            }
        )
        return minute_r_squared_curve(
            pl.DataFrame(rows),
            realized,
            interest_rate=0.0,
            clamp_bound=0.0,
            settlement_divisor=1.0,
            shuffle_count=100,
            shuffle_seed=0,
        )

    white = make_curve("white_noise").filter(pl.col("minute") == 10).row(0, named=True)
    persistent = make_curve("persistent").filter(pl.col("minute") == 10).row(
        0, named=True
    )

    assert white["shuffle_timing_gap"] == pytest.approx(0.0, abs=0.04)
    assert persistent["shuffle_timing_gap"] > 0.20
    assert persistent["iid_excess"] != pytest.approx(
        persistent["shuffle_timing_gap"], abs=1e-6
    )


def test_zero_oracle_sample_is_skipped_without_poisoning_hour() -> None:
    start = datetime(2026, 5, 1)
    samples = pl.DataFrame(
        {
            "market": ["xyz:TEST"] * 3,
            "time_exchange": [
                start.replace(minute=0),
                start.replace(minute=1),
                start.replace(minute=2),
            ],
            "update_class": ["Deployer"] * 3,
            "mark_px": [101.0, 999.0, 103.0],
            "oracle_px": [100.0, 0.0, 100.0],
        }
    )
    realized = pl.DataFrame(
        {
            "market": ["xyz:TEST"],
            "time_exchange": [start + timedelta(hours=1)],
            "funding_rate": [0.02],
        }
    )

    per_hour, _ = reconcile_samples(
        samples,
        realized,
        interest_rate=0.0,
        clamp_bound=0.0,
        settlement_divisor=1.0,
    )

    assert per_hour["sample_count"][0] == 2
    assert per_hour["average_premium"][0] == pytest.approx(0.02)


def test_complete_hours_reject_material_mid_hour_gap() -> None:
    assert MAX_CONSECUTIVE_MISSING_MINUTES == 5
    starts = [datetime(2026, 5, 2), datetime(2026, 5, 2, 1)]
    rows = []
    for hour_index, start in enumerate(starts):
        minutes = list(range(60)) if hour_index else list(range(20)) + list(range(41, 60))
        for minute in minutes:
            rows.append(
                {
                    "market": "xyz:TEST",
                    "time_exchange": start.replace(minute=minute),
                    "update_class": "Deployer",
                    "mark_px": 101.0,
                    "oracle_px": 100.0,
                }
            )
    realized = pl.DataFrame(
        {
            "market": ["xyz:TEST"] * 2,
            "time_exchange": [start + timedelta(hours=1) for start in starts],
            "funding_rate": [0.01, 0.01],
        }
    )

    per_hour, _ = reconcile_samples(
        pl.DataFrame(rows),
        realized,
        interest_rate=0.0,
        clamp_bound=0.0,
        settlement_divisor=1.0,
        require_complete_hours=True,
    )

    assert per_hour["settlement_time"].to_list() == [starts[1] + timedelta(hours=1)]
