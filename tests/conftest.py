"""Shared fixtures for console tests: tiny parquet datasets in a temp data dir."""
from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl
import pytest


def _candles(market: str, n: int = 60, start_price: float = 100.0) -> pl.DataFrame:
    t0 = datetime(2026, 6, 1)
    rows = []
    price = start_price
    for i in range(n):
        o = price
        c = price + (1.0 if i % 3 else -1.5)
        rows.append(
            {
                "dex": market.split(":")[0] if ":" in market else "main",
                "market": market,
                "interval": "1h",
                "open_time_ms": int((t0 + timedelta(hours=i)).timestamp() * 1000),
                "close_time_ms": int((t0 + timedelta(hours=i + 1)).timestamp() * 1000),
                "time_open": t0 + timedelta(hours=i),
                "open": o,
                "high": max(o, c) + 0.5,
                "low": min(o, c) - 0.5,
                "close": c,
                "v": 10.0 + i,
                "n": 5,
            }
        )
        price = c
    return pl.DataFrame(rows)


@pytest.fixture()
def console_data_dir(tmp_path, monkeypatch):
    d = tmp_path / "reports"
    d.mkdir()

    pl.concat([_candles("xyz:AAA"), _candles("km:BBB", start_price=50.0)]).write_parquet(
        d / "study3_candles_1h.parquet"
    )

    t0 = datetime(2026, 6, 1)
    bt_rows = []
    for i in range(40):
        for mkt, pnl in [("xyz:AAA", 0.001 * ((i % 5) - 2)), ("km:BBB", 0.0005)]:
            bt_rows.append(
                {
                    "strategy": "short-only-daily",
                    "rebalance_time": t0 + timedelta(days=i),
                    "market": mkt,
                    "net_pnl": pnl,
                    "funding_pnl": pnl / 2,
                    "price_pnl": pnl / 2,
                    "cost_pnl": 0.0,
                    "turnover": 1.0,
                }
            )
    pl.DataFrame(bt_rows).write_parquet(d / "study3_sc_backtest.parquet")

    pl.DataFrame(
        {
            "strategy": ["short-only-daily"],
            "net_total_return": [-0.70],
            "return_ci_low": [-1.43],
            "return_ci_high": [-0.002],
            "sharpe": [-2.654],
            "sharpe_ci_low": [-5.625],
            "sharpe_ci_high": [-0.007],
            "funding_pnl": [0.185],
            "price_pnl": [-0.838],
            "cost_pnl": [-0.047],
            "max_drawdown": [-0.8],
            "rebalance_count": [40],
            "markets_entered": [2],
        }
    ).write_parquet(d / "study3_sc_summary.parquet")

    fills = []
    for mkt in ["xyz:AAA", "km:BBB"]:
        for seg in ["RTH", "off-hours"]:
            for i in range(10):
                fills.append(
                    {
                        "market": mkt,
                        "segment": seg,
                        "net_markout_1s_bps": -1.0 - i * 0.1,
                        "stale_1s": i == 9,
                        "net_markout_2m_bps": -3.0 - i * 0.1,
                        "stale_2m": False,
                        "net_markout_30s_bps": -2.0 - i * 0.1,
                        "stale_30s": False,
                    }
                )
    pl.DataFrame(fills).write_parquet(d / "study1_fills_l2.parquet")

    monkeypatch.setenv("CHARYBDIS_DATA_DIR", str(d))
    # datasets module caches by mtime; clear between tests
    from charybdis.console import datasets

    datasets._PAYLOAD_CACHE.clear()
    return d
