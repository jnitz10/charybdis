"""Frozen-rule signal computation for the exhaustion-reversal forward test."""

from datetime import date, timedelta

import polars as pl

from charybdis.forward_test import compute_residual_signals, compute_signals


SIGNAL_DAY = date(2026, 7, 10)


def make_panel(
    market: str = "xyz:TEST",
    first_day: date = date(2026, 6, 20),
    days: int = 21,
    closes: list[float] | None = None,
    daily_notional: float = 5_000_000.0,
) -> pl.DataFrame:
    dates = [first_day + timedelta(days=offset) for offset in range(days)]
    if closes is None:
        closes = [100.0] * days
    return pl.DataFrame(
        {
            "market": [market] * days,
            "date": dates,
            "close": closes,
            "volume": [daily_notional / close for close in closes],
        }
    )


def with_final_drop(panel: pl.DataFrame, drop: float = -0.10) -> pl.DataFrame:
    closes = panel["close"].to_list()
    closes[-1] = closes[-4] * (1 + drop)
    return panel.with_columns(pl.Series("close", closes))


def test_qualifying_decline_is_selected_long():
    panel = with_final_drop(make_panel())
    signals = compute_signals(panel, SIGNAL_DAY)
    assert signals.height == 1
    row = signals.row(0, named=True)
    assert row["side"] == 1
    assert row["selected"] is True
    assert row["ret3"] <= -0.08
    assert row["age_days"] == 20


def test_small_decline_does_not_qualify():
    panel = with_final_drop(make_panel(), drop=-0.05)
    assert compute_signals(panel, SIGNAL_DAY).height == 0


def test_rally_is_recorded_as_short_but_not_selected():
    panel = with_final_drop(make_panel(), drop=+0.12)
    signals = compute_signals(panel, SIGNAL_DAY)
    assert signals.height == 1
    row = signals.row(0, named=True)
    assert row["side"] == -1
    assert row["selected"] is False


def test_age_window_gates_young_and_mature_contracts():
    too_young = with_final_drop(
        make_panel(first_day=SIGNAL_DAY - timedelta(days=6), days=7)
    )
    assert compute_signals(too_young, SIGNAL_DAY).height == 0

    mature = with_final_drop(
        make_panel(first_day=SIGNAL_DAY - timedelta(days=60), days=61)
    )
    assert compute_signals(mature, SIGNAL_DAY).height == 0

    week_one_boundary = with_final_drop(
        make_panel(first_day=SIGNAL_DAY - timedelta(days=7), days=8)
    )
    assert compute_signals(week_one_boundary, SIGNAL_DAY).height == 1


def test_left_censored_first_candle_is_excluded():
    panel = with_final_drop(
        make_panel(first_day=date(2026, 1, 1), days=(SIGNAL_DAY - date(2026, 1, 1)).days + 1)
    )
    assert compute_signals(panel, SIGNAL_DAY).height == 0


def test_liquidity_floor_uses_trailing_median_excluding_signal_day():
    thin = with_final_drop(make_panel(daily_notional=500_000.0))
    assert compute_signals(thin, SIGNAL_DAY).height == 0

    # huge signal-day volume must not rescue a thin market
    thin_spike = thin.with_columns(
        pl.when(pl.col("date") == SIGNAL_DAY)
        .then(pl.col("volume") * 100)
        .otherwise(pl.col("volume"))
        .alias("volume")
    )
    assert compute_signals(thin_spike, SIGNAL_DAY).height == 0


def test_largest_decline_wins_selection():
    small = with_final_drop(make_panel("xyz:SMALL"), drop=-0.09)
    big = with_final_drop(make_panel("xyz:BIG"), drop=-0.20)
    signals = compute_signals(pl.concat([small, big]), SIGNAL_DAY)
    assert signals.height == 2
    selected = signals.filter(pl.col("selected"))
    assert selected.height == 1
    assert selected["market"][0] == "xyz:BIG"


def test_residual_market_wide_crash_does_not_qualify():
    # every market falls 10%: raw fires, residual (venue-factor-adjusted) must not
    panels = [
        with_final_drop(make_panel(f"xyz:M{index}"), drop=-0.10) for index in range(5)
    ]
    panel = pl.concat(panels)
    assert compute_signals(panel, SIGNAL_DAY).filter(pl.col("side") == 1).height == 5
    assert compute_residual_signals(panel, SIGNAL_DAY).height == 0


def test_residual_idiosyncratic_crash_qualifies():
    flat = [make_panel(f"xyz:F{index}") for index in range(4)]
    crashed = with_final_drop(make_panel("xyz:CRASH"), drop=-0.12)
    signals = compute_residual_signals(pl.concat(flat + [crashed]), SIGNAL_DAY)
    assert signals.height == 1
    row = signals.row(0, named=True)
    assert row["market"] == "xyz:CRASH"
    assert row["selected"] is True
    assert row["signal_value"] <= -0.08


def test_residual_selection_by_most_negative_residual():
    flat = [make_panel(f"xyz:F{index}") for index in range(4)]
    small = with_final_drop(make_panel("xyz:SMALL"), drop=-0.09)
    big = with_final_drop(make_panel("xyz:BIG"), drop=-0.20)
    signals = compute_residual_signals(pl.concat(flat + [small, big]), SIGNAL_DAY)
    assert signals.height == 2
    assert signals.filter(pl.col("selected"))["market"][0] == "xyz:BIG"


def test_residual_median_includes_left_censored_markets():
    # left-censored markets shape the cross-sectional median even though they
    # cannot themselves signal
    censored_days = (SIGNAL_DAY - date(2026, 1, 1)).days + 1
    censored = [
        with_final_drop(
            make_panel(f"xyz:C{index}", first_day=date(2026, 1, 1), days=censored_days),
            drop=-0.10,
        )
        for index in range(3)
    ]
    crashed = with_final_drop(make_panel("xyz:CRASH"), drop=-0.12)
    signals = compute_residual_signals(pl.concat(censored + [crashed]), SIGNAL_DAY)
    # median ret3 is about -10%, so CRASH's residual is only about -2%: no signal,
    # and the censored markets are excluded as signal rows regardless
    assert signals.height == 0


def test_future_dates_are_ignored():
    panel = with_final_drop(make_panel())
    future_row = pl.DataFrame(
        {
            "market": ["xyz:TEST"],
            "date": [SIGNAL_DAY + timedelta(days=1)],
            "close": [1.0],  # absurd value; must not affect the signal-day rows
            "volume": [1.0],
        }
    )
    signals = compute_signals(pl.concat([panel, future_row]), SIGNAL_DAY)
    assert signals.height == 1
    assert signals["date"][0] == SIGNAL_DAY
