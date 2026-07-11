"""Candle sources for the Chart Lab. Add a source = add a SOURCES entry."""
from __future__ import annotations

import polars as pl

from charybdis.console import datasets, indicators
from charybdis.console.tables import json_value

SOURCES: dict[str, dict] = {
    "study3_1h": {"dataset": "study3_candles_1h", "interval": "1h"},
    "study3_1d": {"dataset": "study3_candles_1d", "interval": "1d"},
}


def list_sources() -> list[dict]:
    out = []
    for sid, cfg in SOURCES.items():
        if not datasets.dataset_exists(cfg["dataset"]):
            continue
        markets = (
            datasets.scan_dataset(cfg["dataset"])
            .select(pl.col("market").unique().sort())
            .collect()["market"]
            .to_list()
        )
        out.append({"id": sid, "interval": cfg["interval"], "markets": markets})
    return out


def get_candles(source: str, market: str, ind: list[str]) -> dict:
    cfg = SOURCES[source]  # KeyError -> 404 in route
    df = (
        datasets.scan_dataset(cfg["dataset"])
        .filter(pl.col("market") == market)
        .sort("open_time_ms")
        .select(["open_time_ms", "open", "high", "low", "close", "v"])
        .collect()
    )
    if df.height == 0:
        raise ValueError(f"no rows for market {market!r} in {source}")
    ohlcv = df.rename({"v": "volume"}).select(["open", "high", "low", "close", "volume"])
    payload = {
        "source": source,
        "market": market,
        "interval": cfg["interval"],
        "time": (df["open_time_ms"] // 1000).to_list(),
        "open": df["open"].to_list(),
        "high": df["high"].to_list(),
        "low": df["low"].to_list(),
        "close": df["close"].to_list(),
        "volume": df["volume" if "volume" in df.columns else "v"].to_list(),
        "indicators": [],
    }
    for spec_str in ind:
        spec, out = indicators.compute(spec_str, ohlcv)
        payload["indicators"].append(
            {
                "id": spec_str,
                "name": spec.name,
                "display": spec.display,
                "series": {c: [json_value(v) for v in out[c].to_list()] for c in out.columns},
            }
        )
    return payload
