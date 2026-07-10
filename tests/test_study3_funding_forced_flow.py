from datetime import datetime, timedelta

import polars as pl
import pytest


def test_event_rate_uses_bucket_exposure_hours_and_exact_rate_ratio() -> None:
    from charybdis.study3_funding_forced_flow import summarize_event_rates

    start = datetime(2026, 1, 1)
    exposure = pl.DataFrame(
        [
            ("SKHX", start, "negative", 2.0, 1, "SKHX|2026-01-01T00:00:00"),
            ("SMSN", start, "negative", 2.0, 1, "SMSN|2026-01-01T00:00:00"),
            ("SKHX", start + timedelta(hours=6), "ge_100pct", 1.0, 2, "SKHX|2026-01-01T06:00:00"),
            ("SMSN", start + timedelta(hours=6), "ge_100pct", 1.0, 1, "SMSN|2026-01-01T06:00:00"),
        ],
        schema=[
            "market",
            "block_start",
            "funding_bucket",
            "exposure_hours",
            "event_count",
            "cluster_key",
        ],
        orient="row",
    )

    rates, ratios = summarize_event_rates(exposure, n_resamples=2_000, seed=7, min_clusters=2)
    by_bucket = {row["funding_bucket"]: row for row in rates.iter_rows(named=True)}

    assert by_bucket["negative"]["event_count"] == 2
    assert by_bucket["negative"]["exposure_hours"] == 4.0
    assert by_bucket["negative"]["event_rate_per_market_hour"] == 0.5
    assert by_bucket["ge_100pct"]["event_count"] == 3
    assert by_bucket["ge_100pct"]["exposure_hours"] == 2.0
    assert by_bucket["ge_100pct"]["event_rate_per_market_hour"] == 1.5
    assert ratios.row(0, named=True)["rate_ratio"] == pytest.approx(3.0)


def test_market_cluster_diagnostic_prevents_pooled_timing_false_positive() -> None:
    from charybdis.run_study3_funding_forced_flow import ff_conclusion
    from charybdis.study3_funding_forced_flow import market_clustered_rate_ratio

    start = datetime(2026, 1, 1)
    rows = []
    for market in ("SKHX", "SMSN"):
        for block in range(40):
            bucket = "negative" if block < 20 else "ge_100pct"
            rows.append(
                (
                    market,
                    start + timedelta(hours=6 * block),
                    bucket,
                    6.0,
                    8 if bucket == "negative" else 7,
                    f"{market}|{block}",
                )
            )
    exposure = pl.DataFrame(
        rows,
        schema=[
            "market",
            "block_start",
            "funding_bucket",
            "exposure_hours",
            "event_count",
            "cluster_key",
        ],
        orient="row",
    )
    diagnostic = market_clustered_rate_ratio(exposure, n_resamples=2_000, seed=9)
    ratios = pl.DataFrame(
        [
            ("ALL", 0.875, 0.80, 0.98),
            ("SKHX", 0.875, 0.70, 1.08),
            ("SMSN", 0.875, 0.69, 1.09),
        ],
        schema=["scope", "rate_ratio", "ci_low", "ci_high"],
        orient="row",
    )

    assert diagnostic["clusters"] == 2
    assert diagnostic["low_cluster"] is True
    assert diagnostic["ci_low"] is None
    assert diagnostic["ci_high"] is None
    conclusion = ff_conclusion(ratios)
    assert "no timing effect" in conclusion
    assert "market-selection only" in conclusion
    assert "below 1" in conclusion


def test_hazard_probability_matches_hand_built_24h_ground_truth() -> None:
    from charybdis.study3_funding_forced_flow import hazard_table

    start = datetime(2026, 1, 1)
    conditioning = pl.DataFrame(
        [
            ("SKHX", start, "negative"),
            ("SKHX", start + timedelta(hours=30), "negative"),
            ("SMSN", start, "ge_100pct"),
            ("SMSN", start + timedelta(hours=30), "ge_100pct"),
            ("SMSN", start + timedelta(hours=60), "ge_100pct"),
        ],
        schema=["market", "conditioning_time", "funding_bucket"],
        orient="row",
    )
    events = pl.DataFrame(
        [
            ("SKHX", start + timedelta(hours=12)),
            ("SMSN", start + timedelta(hours=24)),
            ("SMSN", start + timedelta(hours=31)),
        ],
        schema=["market", "start_time"],
        orient="row",
    )

    result = hazard_table(conditioning, events)
    by_bucket = {row["funding_bucket"]: row for row in result.iter_rows(named=True)}

    assert by_bucket["negative"]["conditioning_observations"] == 2
    assert by_bucket["negative"]["event_within_24h_count"] == 1
    assert by_bucket["negative"]["probability_event_within_24h"] == 0.5
    assert by_bucket["ge_100pct"]["conditioning_observations"] == 3
    assert by_bucket["ge_100pct"]["event_within_24h_count"] == 2
    assert by_bucket["ge_100pct"]["probability_event_within_24h"] == pytest.approx(2 / 3)


def test_near_daily_events_flag_24h_saturation_but_2h_is_informative() -> None:
    from charybdis.study3_funding_forced_flow import hazard_table

    start = datetime(2026, 1, 1)
    conditioning = pl.DataFrame(
        [("SKHX", start + timedelta(hours=hour), "negative") for hour in range(24)],
        schema=["market", "conditioning_time", "funding_bucket"],
        orient="row",
    )
    events = pl.DataFrame(
        [
            ("SKHX", start + timedelta(minutes=30)),
            ("SKHX", start + timedelta(hours=24, minutes=30)),
        ],
        schema=["market", "start_time"],
        orient="row",
    )

    daily = hazard_table(conditioning, events, horizon=timedelta(hours=24)).row(
        0, named=True
    )
    short = hazard_table(conditioning, events, horizon=timedelta(hours=2)).row(
        0, named=True
    )

    assert daily["coverage_saturated"] is True
    assert daily["probability_event_within_horizon"] == pytest.approx(1.0)
    assert short["coverage_saturated"] is False
    assert 0.0 < short["probability_event_within_horizon"] < 0.5


def test_conditioning_bucket_is_causal_but_hazard_outcome_can_look_forward() -> None:
    from charybdis.study3_funding_forced_flow import (
        causal_conditioning_buckets,
        hazard_table,
    )

    start = datetime(2026, 1, 1)
    funding = pl.DataFrame(
        [
            ("SKHX", start, -0.0001),
            ("SKHX", start + timedelta(hours=11), 0.001),
        ],
        schema=["market", "time_exchange", "funding_rate"],
        orient="row",
    )
    times = pl.DataFrame(
        [("SKHX", start + timedelta(hours=10))],
        schema=["market", "conditioning_time"],
        orient="row",
    )
    future_event = pl.DataFrame(
        [("SKHX", start + timedelta(hours=12))],
        schema=["market", "start_time"],
        orient="row",
    )

    causal = causal_conditioning_buckets(funding, times)
    hazard = hazard_table(causal, future_event).row(0, named=True)

    assert causal.row(0, named=True)["funding_settlement_time"] == start
    assert causal.row(0, named=True)["funding_bucket"] == "negative"
    assert hazard["event_within_24h_count"] == 1


def test_wallet_bridge_matches_only_cohort_wallets_in_strictly_later_bursts() -> None:
    from charybdis.study3_funding_forced_flow import wallet_bridge

    start = datetime(2026, 1, 1)
    events = pl.DataFrame(
        [
            ("SKHX", start, "BUY", ["match", "never_later"], "ge_100pct"),
            ("SMSN", start + timedelta(hours=1), "SELL", ["match", "event_only"], "negative"),
            ("SKHX", start + timedelta(hours=2), "BUY", ["second_match"], "ge_100pct"),
            ("SKHX", start + timedelta(hours=3), "SELL", ["second_match"], "0_to_25pct"),
        ],
        schema=["market", "start_time", "direction", "wallets", "funding_bucket"],
        orient="row",
    )

    detail, summary = wallet_bridge(
        events,
        window_end=start + timedelta(hours=30),
        min_forward_window=timedelta(hours=24),
    )
    matched = set(detail.filter(pl.col("appeared_in_later_burst"))["wallet"].to_list())

    assert set(detail["wallet"].to_list()) == {"match", "never_later", "second_match"}
    assert matched == {"match", "second_match"}
    assert "event_only" not in detail["wallet"].to_list()
    assert summary["high_regime_long_accumulator_wallets"] == 3
    assert summary["later_burst_taker_wallets"] == 2
    assert summary["bridge_fraction"] == pytest.approx(2 / 3)


def test_wallet_bridge_equal_control_reappearance_has_zero_signal() -> None:
    from charybdis.study3_funding_forced_flow import wallet_bridge

    start = datetime(2026, 1, 1)
    cohort_events = [
        ("BUY", "ge_100pct", "high_repeat"),
        ("BUY", "ge_100pct", "high_once"),
        ("BUY", "negative", "low_repeat"),
        ("BUY", "0_to_25pct", "low_once"),
        ("SELL", "ge_100pct", "sell_repeat"),
        ("SELL", "ge_100pct", "sell_once"),
        ("SELL", "25_to_100pct", "other_repeat"),
        ("SELL", "25_to_100pct", "other_once"),
    ]
    rows = [
        ("SKHX", start, direction, [wallet], bucket)
        for direction, bucket, wallet in cohort_events
    ]
    rows.extend(
        ("SKHX", start + timedelta(hours=2), "SELL", [wallet], "25_to_100pct")
        for wallet in ("high_repeat", "low_repeat", "sell_repeat", "other_repeat")
    )
    rows.append(
        ("SKHX", start + timedelta(hours=29), "BUY", ["late_censored"], "ge_100pct")
    )
    events = pl.DataFrame(
        rows,
        schema=["market", "start_time", "direction", "wallets", "funding_bucket"],
        orient="row",
    )

    _, summary = wallet_bridge(
        events,
        window_end=start + timedelta(hours=30),
        min_forward_window=timedelta(hours=24),
    )

    assert summary["bridge_fraction"] == pytest.approx(0.5)
    assert summary["high_regime_long_accumulator_wallets"] == 2
    assert summary["right_censored_high_regime_long_wallets"] == 1
    assert summary["low_apr_buy_control_fraction"] == pytest.approx(0.5)
    assert summary["high_apr_sell_control_fraction"] == pytest.approx(0.5)
    assert summary["proxy_population_control_fraction"] == pytest.approx(0.5)
    assert summary["bridge_signal_difference"] == pytest.approx(0.0)


def test_exposure_panel_assigns_events_to_causal_funding_intervals() -> None:
    from charybdis.study3_funding_forced_flow import build_exposure_panel

    start = datetime(2026, 1, 1)
    funding = pl.DataFrame(
        [
            ("SKHX", start, -0.0001),
            ("SKHX", start + timedelta(hours=2), 0.001),
        ],
        schema=["market", "time_exchange", "funding_rate"],
        orient="row",
    )
    events = pl.DataFrame(
        [
            ("SKHX", start + timedelta(minutes=30)),
            ("SKHX", start + timedelta(hours=2, minutes=30)),
            ("SKHX", start + timedelta(hours=3, minutes=30)),
        ],
        schema=["market", "start_time"],
        orient="row",
    )

    panel = build_exposure_panel(
        funding,
        events,
        window_start=start,
        window_end=start + timedelta(hours=4),
    )
    totals = {
        row["funding_bucket"]: row
        for row in panel.group_by("funding_bucket").agg(
            pl.col("exposure_hours").sum(), pl.col("event_count").sum()
        ).iter_rows(named=True)
    }

    assert totals["negative"]["exposure_hours"] == 2.0
    assert totals["negative"]["event_count"] == 1
    assert totals["ge_100pct"]["exposure_hours"] == 2.0
    assert totals["ge_100pct"]["event_count"] == 2


def test_sign_size_deciles_are_exposure_weighted_and_keep_sign() -> None:
    from charybdis.study3_funding_forced_flow import add_sign_size_deciles

    panel = pl.DataFrame(
        {
            "annualized_rate": [float(value) * (-1 if value % 2 else 1) for value in range(1, 11)],
            "exposure_hours": [1.0] * 10,
        }
    )

    result = add_sign_size_deciles(panel).sort(pl.col("annualized_rate").abs())

    assert result["sign_size_decile"][0] == "negative_D01"
    assert result["sign_size_decile"][-1] == "nonnegative_D10"
