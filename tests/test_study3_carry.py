from datetime import datetime, timedelta
import math

import polars as pl
import pytest


def _funding(rows: list[tuple[str, datetime, float]]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=["market", "time_exchange", "funding_rate"], orient="row")


def test_shifted_funding_changes_causal_decile_pnl() -> None:
    from charybdis.study3_carry import funding_window, position_targets, signal_cross_section

    rebalance = datetime(2026, 1, 8)
    rows = []
    for hours, a, b in [(-1, 0.00, 0.05), (0, 0.10, 0.00), (1, 0.02, 0.50)]:
        rows.extend([("x:A", rebalance + timedelta(hours=hours), a), ("x:B", rebalance + timedelta(hours=hours), b)])
    funding = _funding(rows)
    shifted = funding.with_columns(pl.col("time_exchange") + pl.duration(hours=1))

    def pnl(frame: pl.DataFrame) -> float:
        mapping = {
            market: sorted(zip(group["time_exchange"].to_list(), group["funding_rate"].to_list()))
            for (market,), group in frame.partition_by("market", as_dict=True).items()
        }
        signals = signal_cross_section(mapping, ["x:A", "x:B"], rebalance, min_observations=1)
        positions = position_targets(signals, long_short=False)
        return sum(-weight * sum(funding_window(mapping[market], rebalance, rebalance + timedelta(hours=2))) for market, weight in positions.items())

    original = pnl(funding)
    delayed = pnl(shifted)

    assert original != delayed


def test_price_return_uses_only_candles_strictly_after_rebalance() -> None:
    import charybdis.study3_carry as carry
    from charybdis.run_study3_carry import _price_blocks

    rebalance = datetime(2026, 1, 1)
    candles = [
        (rebalance + timedelta(hours=h), rebalance + timedelta(hours=h + 1) - timedelta(milliseconds=1), price)
        for h, price in enumerate([100.0, 120.0, 180.0])
    ]

    blocks, complete = _price_blocks(candles, rebalance, rebalance + timedelta(hours=3))

    assert not hasattr(carry, "candle_period_return")
    assert complete
    assert sum(block[2] for block in blocks) == 0.5


def test_position_targets_short_high_funders_and_long_low_funders() -> None:
    from charybdis.study3_carry import position_targets

    signals = pl.DataFrame({"market": [f"x:{i:02d}" for i in range(20)], "signal": range(20)})

    short_only = position_targets(signals, long_short=False)
    long_short = position_targets(signals, long_short=True)

    assert short_only["x:19"] < 0
    assert long_short["x:19"] < 0
    assert long_short["x:00"] > 0


def test_high_funder_short_loses_on_post_entry_squeeze() -> None:
    from charybdis.run_study3_carry import _run_targets

    rebalance = datetime(2026, 1, 8)
    funding_map = {
        market: [(rebalance - timedelta(hours=167 - hour), rate) for hour in range(168)]
        for market, rate in [("x:HIGH", 0.01), ("x:LOW", 0.0)]
    }
    candle_map = {
        "x:HIGH": [
            (rebalance - timedelta(days=7), rebalance - timedelta(days=7) + timedelta(hours=1) - timedelta(milliseconds=1), 120.0),
            (rebalance - timedelta(hours=1), rebalance - timedelta(milliseconds=1), 100.0),
            (rebalance + timedelta(hours=1), rebalance + timedelta(hours=2) - timedelta(milliseconds=1), 100.0),
            (rebalance + timedelta(hours=2), rebalance + timedelta(hours=3) - timedelta(milliseconds=1), 150.0),
        ],
        "x:LOW": [
            (rebalance - timedelta(hours=1), rebalance - timedelta(milliseconds=1), 100.0),
            (rebalance + timedelta(hours=1), rebalance + timedelta(hours=2) - timedelta(milliseconds=1), 100.0),
            (rebalance + timedelta(hours=2), rebalance + timedelta(hours=3) - timedelta(milliseconds=1), 100.0),
        ],
    }
    fees = pl.DataFrame({"dex": ["x"], "effective_taker_bps": [0.0]})
    spreads = pl.DataFrame({
        "market": ["x:HIGH", "x:LOW"], "half_spread_bps": [0.0, 0.0],
        "spread_source": ["synthetic", "synthetic"], "market_class": ["synthetic", "synthetic"],
    })

    result = _run_targets(
        strategy="synthetic", periods=[(rebalance, rebalance + timedelta(hours=3))],
        candidates=["x:HIGH", "x:LOW"], funding_map=funding_map, candle_map=candle_map,
        fees=fees, spreads=spreads, long_short=False,
    )

    assert result.filter(pl.col("market") == "x:HIGH")["position"].unique().to_list() == [-1.0]
    assert result["net_pnl"].sum() < 0


def test_reverse_causation_labels_pre_rebalance_drop_loss() -> None:
    from charybdis.run_study3_carry import _run_targets

    rebalance = datetime(2026, 1, 8)
    funding_map = {
        market: [(rebalance - timedelta(hours=167 - hour), rate) for hour in range(168)]
        for market, rate in [("x:HIGH", 0.01), ("x:LOW", 0.0)]
    }
    candles = {
        "x:HIGH": [
            (rebalance - timedelta(days=7), rebalance - timedelta(days=7) + timedelta(hours=1), 120.0),
            (rebalance - timedelta(hours=1), rebalance, 100.0),
            (rebalance + timedelta(hours=1), rebalance + timedelta(hours=2), 100.0),
            (rebalance + timedelta(hours=2), rebalance + timedelta(hours=3), 150.0),
        ],
        "x:LOW": [
            (rebalance - timedelta(hours=1), rebalance, 100.0),
            (rebalance + timedelta(hours=1), rebalance + timedelta(hours=2), 100.0),
            (rebalance + timedelta(hours=2), rebalance + timedelta(hours=3), 100.0),
        ],
    }
    fees = pl.DataFrame({"dex": ["x"], "effective_taker_bps": [0.0]})
    spreads = pl.DataFrame({
        "market": ["x:HIGH", "x:LOW"], "half_spread_bps": [0.0, 0.0],
        "spread_source": ["synthetic", "synthetic"], "market_class": ["synthetic", "synthetic"],
    })

    result = _run_targets(
        strategy="synthetic", periods=[(rebalance, rebalance + timedelta(hours=3))],
        candidates=["x:HIGH", "x:LOW"], funding_map=funding_map, candle_map=candles,
        fees=fees, spreads=spreads, long_short=False,
    ).filter(pl.col("position") < 0)

    assert result["pre_rebalance_return"].unique().to_list() == pytest.approx([-1 / 6])
    assert result["price_loss_path"].unique().to_list() == ["pre_rebalance_drop"]


def test_decile_assignment_selects_cross_section_extremes() -> None:
    from charybdis.study3_carry import assign_deciles

    signals = pl.DataFrame({"market": [f"x:{i:02d}" for i in range(20)], "signal": range(20)})

    result = assign_deciles(signals)

    assert result.filter(pl.col("decile") == "top")["market"].to_list() == ["x:18", "x:19"]
    assert result.filter(pl.col("decile") == "bottom")["market"].to_list() == ["x:00", "x:01"]


def test_cost_uses_fee_table_value_as_single_source() -> None:
    from charybdis.study3_carry import turnover_cost

    fee_table = pl.DataFrame({"dex": ["hyna"], "effective_taker_bps": [0.49995]})

    cost = turnover_cost("hyna:ABC", turnover=1.25, half_spread_bps=2.0, fee_table=fee_table)

    assert cost == 1.25 * (0.49995 + 2.0) / 10_000


def test_trailing_hedge_beta_recovers_known_synthetic_beta() -> None:
    from charybdis.study3_carry import trailing_hedge_beta

    start = datetime(2026, 1, 1)
    rows = []
    hedge_log_price = target_log_price = 0.0
    for hour in range(101):
        if hour:
            hedge_return = (hour % 7 - 3) / 1000
            hedge_log_price += hedge_return
            target_log_price += 2.0 * hedge_return
        timestamp = start + timedelta(hours=hour)
        rows.extend([("x:TARGET", timestamp, math.exp(target_log_price)), ("x:HEDGE", timestamp, math.exp(hedge_log_price))])
    candles = pl.DataFrame(rows, schema=["market", "time_open", "close"], orient="row")

    beta = trailing_hedge_beta(candles, start + timedelta(hours=101), "x:TARGET", ["x:HEDGE"])

    assert beta == pytest.approx(2.0)


def test_candle_truncated_market_exits_when_price_coverage_ends() -> None:
    from charybdis.run_study3_carry import _price_blocks, _price_known_at

    start = datetime(2026, 1, 1)
    rows = [
        (start + timedelta(hours=h), start + timedelta(hours=h + 1) - timedelta(milliseconds=1), 100.0 + h)
        for h in range(3)
    ]

    assert _price_known_at(rows, start + timedelta(hours=2))
    blocks, complete = _price_blocks(rows, start + timedelta(hours=2), start + timedelta(hours=5))
    assert blocks == []
    assert not complete
    assert not _price_known_at(rows, start + timedelta(hours=4))

    partial_rows = [
        (start + timedelta(hours=h), start + timedelta(hours=h + 1) - timedelta(milliseconds=1), 100.0 + h)
        for h in range(5)
    ]
    blocks, complete = _price_blocks(partial_rows, start + timedelta(hours=2), start + timedelta(hours=10))
    assert not complete
    assert sum((end - begin).total_seconds() for begin, end, _ in blocks) == pytest.approx(3 * 3600 - 0.001)
    assert blocks[-1][1] == partial_rows[-1][1]


def test_portfolio_bootstrap_resamples_netted_periods_jointly() -> None:
    from charybdis.run_study3_carry import summarize

    start = datetime(2026, 1, 1)
    rows = []
    for period in range(10):
        rebalance = start + timedelta(days=period)
        shock = 0.10 * (period + 1)
        for market, pnl in [("x:SHORT", -shock), ("x:HEDGE", shock + 0.01)]:
            rows.append({
                "strategy": "synthetic-hedged", "rebalance_time": rebalance,
                "hold_end_time": rebalance + timedelta(days=1),
                "block_start": rebalance, "block_end": rebalance + timedelta(days=1),
                "market": market, "position": -1.0 if market == "x:SHORT" else 1.0,
                "funding_pnl": 0.0, "price_pnl": pnl, "cost_pnl": 0.0,
                "net_pnl": pnl, "period_hours": 24.0,
                "pre_rebalance_return": 0.0, "price_loss_path": "forward_squeeze",
                "coverage_complete_for_hold": True,
                "cluster_key": f"{market}|{rebalance.isoformat()}",
                "block_start_hour_utc": 0, "block_offset_hours": 0.0,
            })
    backtest = pl.DataFrame(rows)

    result = summarize(backtest, backtest).row(0, named=True)

    assert result["net_total_return"] == pytest.approx(0.10)
    assert result["return_ci_low"] == pytest.approx(0.10)
    assert result["return_ci_high"] == pytest.approx(0.10)


def test_report_includes_required_carry_caveats() -> None:
    from charybdis.run_study3_carry import DOC_PATH

    report = DOC_PATH.read_text()

    assert "## Reverse-causation diagnostic" in report
    assert "price-residual dominated" in report
    assert "1–2-settlement asymmetry" in report
    assert "no terminal-liquidation cost" in report
    assert "No verdict is rendered between these interpretations" in report
