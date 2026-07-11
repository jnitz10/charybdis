"""Candle sources for the Chart Lab.

Add a parquet-backed source = add a SOURCES entry. Raw-trade sources
(RAW_SOURCES) build OHLCV server-side from the T-TRADES flat-file archive.
"""
from __future__ import annotations

import polars as pl

from charybdis.console import datasets, indicators, rawdata
from charybdis.console.tables import json_value


class MarketNotFound(LookupError):
    """Requested market has no rows in the source dataset."""

SOURCES: dict[str, dict] = {
    "study3_1h": {"dataset": "study3_candles_1h", "interval": "1h"},
    "study3_1d": {"dataset": "study3_candles_1d", "interval": "1d"},
}

# source id -> bar interval, aggregated from raw T-TRADES ticks
RAW_SOURCES: dict[str, str] = {
    "raw_trades_1m": "1m",
    "raw_trades_5m": "5m",
    "raw_trades_1h": "1h",
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
    raw_markets = rawdata.trade_markets()
    if raw_markets:
        for sid, every in RAW_SOURCES.items():
            out.append({"id": sid, "interval": every, "markets": raw_markets})
    return out


def _ohlcv_frame(source: str, market: str) -> tuple[pl.DataFrame, str, list[str]]:
    """Collect (time_s, open, high, low, close, volume), bar interval, warnings."""
    if source in RAW_SOURCES:
        every = RAW_SOURCES[source]
        try:
            df, warnings = rawdata.trade_candles(market, every)
        except LookupError as e:
            raise MarketNotFound(str(e)) from e
        return df, every, warnings
    cfg = SOURCES[source]  # KeyError -> 404 in route
    df = (
        datasets.scan_dataset(cfg["dataset"])
        .filter(pl.col("market") == market)
        .sort("open_time_ms")
        .select(
            (pl.col("open_time_ms") // 1000).alias("time_s"),
            "open",
            "high",
            "low",
            "close",
            pl.col("v").alias("volume"),
        )
        .collect()
    )
    if df.height == 0:
        raise MarketNotFound(f"no rows for market {market!r} in {source}")
    return df, cfg["interval"], []


def get_candles(source: str, market: str, ind: list[str]) -> dict:
    df, interval, warnings = _ohlcv_frame(source, market)
    ohlcv = df.select(["open", "high", "low", "close", "volume"])
    payload = {
        "source": source,
        "market": market,
        "interval": interval,
        "warnings": warnings,
        "time": df["time_s"].to_list(),
        "open": df["open"].to_list(),
        "high": df["high"].to_list(),
        "low": df["low"].to_list(),
        "close": df["close"].to_list(),
        "volume": df["volume"].to_list(),
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
