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
    # module-level caches key on mtime; clear between tests
    from charybdis.console import datasets, rawdata

    datasets._PAYLOAD_CACHE.clear()
    rawdata._INDEX_CACHE.clear()
    rawdata._CANDLE_CACHE.clear()
    return d


L2_TRADES_HEADER = (
    "time_exchange;time_coinapi;guid;price;base_amount;taker_side;"
    "id_exch_guid;id_exch_int_inc;order_id_maker;order_id_taker"
)
L4_TRADES_HEADER = L2_TRADES_HEADER + ";user_taker;user_maker"


def write_gz(path, text: str) -> None:
    import gzip

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(text.encode()))


def l2_trades_csv(day: str, prices: list[float]) -> str:
    rows = [
        f"{day}T10:00:{i:02d}.0370000;{day}T10:00:{i:02d}.1000000;g{i};{px};0.5;BUY;;1;;"
        for i, px in enumerate(prices)
    ]
    return "\n".join([L2_TRADES_HEADER, *rows, ""])


def l4_trades_csv(day: str, prices: list[float]) -> str:
    rows = [
        f"{day}T11:00:{i:02d}.0370000;{day}T11:00:{i:02d}.1000000;g{i};{px};2.0;SELL;;1;;;0xaa;0xbb"
        for i, px in enumerate(prices)
    ]
    return "\n".join([L4_TRADES_HEADER, *rows, ""])


@pytest.fixture()
def raw_data_dir(console_data_dir, tmp_path):
    """Tiny raw CoinAPI archive next to the reports dir (raw root = tmp_path)."""
    sc = "SC-HYPERLIQUID_DPERP_KM_US500_USDC+S-KM__003AUS500.csv.gz"
    sc4 = "SC-HYPERLIQUIDL4_DPERP_KM_US500_USDC+S-KM__003AUS500.csv.gz"
    trades = tmp_path / "T-TRADES"
    write_gz(
        trades / "D-20260311/E-HYPERLIQUID" / f"IDDI-1+{sc}",
        l2_trades_csv("2026-03-11", [100.0, 101.0, 99.0]),
    )
    # 2026-03-12 is covered by BOTH eras: candles must keep only the L4 side
    write_gz(
        trades / "D-20260312/E-HYPERLIQUID" / f"IDDI-1+{sc}",
        l2_trades_csv("2026-03-12", [500.0, 500.0]),
    )
    write_gz(
        trades / "D-2026031211/E-HYPERLIQUIDL4" / f"IDDI-2+{sc4}",
        l4_trades_csv("2026-03-12", [102.0, 103.0]),
    )
    write_gz(
        tmp_path / "T-HLSYSTEMEVENTS/D-2026031211/E-HYPERLIQUIDL4.csv.gz",
        "time_exchange;time_coinapi;exchange_id;block_number;event_type;json_payload\n"
        '2026-03-12T11:00:08.3575243;2026-03-12T11:00:08.5069781;HYPERLIQUIDL4;1;Evt;{"a":1}\n',
    )
    write_gz(
        tmp_path / "T-HLORACLEPRICES/D-2026031211/E-HYPERLIQUIDL4/IDDI-3+S-GOLD.csv.gz",
        "time_exchange;time_coinapi;px\n2026-03-12T11:00:00.0000000;2026-03-12T11:00:00.1000000;2411.5\n",
    )
    # loose parquet at the data root and a parts directory under reports/
    pl.DataFrame({"coin": ["GOLD"], "funding_rate": [0.0001]}).write_parquet(
        tmp_path / "loose_funding.parquet"
    )
    parts = console_data_dir / "parts_ds"
    parts.mkdir()
    pl.DataFrame({"market": ["a"], "x": [1.0]}).write_parquet(parts / "p1.parquet")
    pl.DataFrame({"market": ["b"], "x": [2.0]}).write_parquet(parts / "p2.parquet")
    return tmp_path
