"""Generic backtest viewer backend.

A backtest source is a loader producing per-period returns [time, ret].
Register new backtests by adding a loader to PERIOD_RETURN_LOADERS and a
strategy lister to _STRATEGY_LISTERS.
"""
from __future__ import annotations

import math
from typing import Callable

import polars as pl

from charybdis.console import datasets
from charybdis.console.tables import json_value

_ROLLING_WINDOW = 30
_SECONDS_PER_YEAR = 365 * 24 * 3600


def _load_study3_carry(strategy: str) -> pl.DataFrame:
    return (
        datasets.scan_dataset("study3_sc_backtest")
        .filter(pl.col("strategy") == strategy)
        .group_by("rebalance_time")
        .agg(pl.col("net_pnl").sum().alias("ret"))
        .sort("rebalance_time")
        .rename({"rebalance_time": "time"})
        .collect()
    )


def _list_study3_strategies() -> list[str]:
    if not datasets.dataset_exists("study3_sc_backtest"):
        return []
    return (
        datasets.scan_dataset("study3_sc_backtest")
        .select(pl.col("strategy").unique().sort())
        .collect()["strategy"]
        .to_list()
    )


PERIOD_RETURN_LOADERS: dict[str, Callable[[str], pl.DataFrame]] = {
    "study3-carry": _load_study3_carry,
}

_STRATEGY_LISTERS: dict[str, Callable[[], list[str]]] = {
    "study3-carry": _list_study3_strategies,
}

_TITLES = {"study3-carry": "Study 3 — funding carry"}


def list_backtests() -> list[dict]:
    out = []
    for source, lister in _STRATEGY_LISTERS.items():
        for strategy in lister():
            out.append(
                {
                    "id": f"{source}:{strategy}",
                    "source": source,
                    "strategy": strategy,
                    "title": f"{_TITLES[source]} · {strategy}",
                }
            )
    return out


def _summary_row(source: str, strategy: str) -> dict | None:
    if source != "study3-carry" or not datasets.dataset_exists("study3_sc_summary"):
        return None
    df = (
        datasets.scan_dataset("study3_sc_summary")
        .filter(pl.col("strategy") == strategy)
        .collect()
    )
    if df.height == 0:
        return None
    return {k: json_value(v) for k, v in df.row(0, named=True).items()}


def get_backtest(bt_id: str) -> dict:
    source, _, strategy = bt_id.partition(":")
    loader = PERIOD_RETURN_LOADERS[source]  # KeyError -> 404 in route
    df = loader(strategy)
    if df.height == 0:
        raise KeyError(bt_id)

    times = [int(t.timestamp()) for t in df["time"].to_list()]
    rets = df["ret"].to_list()

    equity, dd, peak, acc = [], [], -math.inf, 0.0
    for r in rets:
        acc += r
        peak = max(peak, acc)
        equity.append(acc)
        dd.append(acc - peak)

    dt = _median_dt_seconds(times)
    ppy = _SECONDS_PER_YEAR / dt if dt else 0.0
    rolling = _rolling_sharpe(rets, ppy)

    monthly = (
        df.group_by(pl.col("time").dt.strftime("%Y-%m").alias("ym"))
        .agg(pl.col("ret").sum())
        .sort("ym")
    )

    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1) if len(rets) > 1 else 0.0
    sharpe = mean / math.sqrt(var) * math.sqrt(ppy) if var > 0 else None

    return {
        "id": bt_id,
        "title": f"{_TITLES.get(source, source)} · {strategy}",
        "stats": {
            "total_return": equity[-1],
            "sharpe": json_value(sharpe) if sharpe is not None else None,
            "max_drawdown": min(dd),
            "periods": len(rets),
            "start": times[0],
            "end": times[-1],
        },
        "equity": [{"t": t, "v": v} for t, v in zip(times, equity)],
        "drawdown": [{"t": t, "v": v} for t, v in zip(times, dd)],
        "rolling_sharpe": [
            {"t": t, "v": v} for t, v in zip(times, rolling) if v is not None
        ],
        "monthly": [{"ym": ym, "ret": r} for ym, r in monthly.rows()],
        "summary": _summary_row(source, strategy),
    }


def _median_dt_seconds(times: list[int]) -> float:
    if len(times) < 2:
        return 0.0
    diffs = sorted(b - a for a, b in zip(times, times[1:]))
    return float(diffs[len(diffs) // 2])


def _rolling_sharpe(rets: list[float], ppy: float) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(rets)):
        if i + 1 < _ROLLING_WINDOW:
            out.append(None)
            continue
        window = rets[i + 1 - _ROLLING_WINDOW : i + 1]
        mean = sum(window) / len(window)
        var = sum((r - mean) ** 2 for r in window) / (len(window) - 1)
        out.append(mean / math.sqrt(var) * math.sqrt(ppy) if var > 0 else None)
    return out
