"""Technical-indicator registry. Add an indicator = write one decorated function.

Indicator functions take an OHLCV DataFrame (open, high, low, close, volume)
and their params, and return a DataFrame of output series (same height).
`display` controls Chart Lab placement: "overlay" on the price chart,
"pane" in its own sub-chart.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import polars as pl

REGISTRY: dict[str, "IndicatorSpec"] = {}


@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    params: dict[str, int | float]  # ordered defaults; order = positional parse order
    display: str  # "overlay" | "pane"
    fn: Callable[..., pl.DataFrame]


def indicator(name: str, params: dict[str, int | float], display: str):
    def deco(fn: Callable[..., pl.DataFrame]):
        REGISTRY[name] = IndicatorSpec(name, params, display, fn)
        return fn

    return deco


def registry_meta() -> list[dict]:
    return [
        {"name": s.name, "params": dict(s.params), "display": s.display}
        for s in REGISTRY.values()
    ]


def compute(spec_str: str, ohlcv: pl.DataFrame) -> tuple[IndicatorSpec, pl.DataFrame]:
    parts = spec_str.split(":")
    name, raw_params = parts[0], parts[1:]
    spec = REGISTRY.get(name)
    if spec is None:
        raise ValueError(f"unknown indicator: {name}")
    if len(raw_params) > len(spec.params):
        raise ValueError(f"{name}: too many params (max {len(spec.params)})")
    kwargs: dict[str, int | float] = dict(spec.params)
    for (pname, default), raw in zip(spec.params.items(), raw_params):
        try:
            kwargs[pname] = type(default)(raw)
        except ValueError as e:
            raise ValueError(f"{name}: bad param {pname}={raw!r}") from e
    return spec, spec.fn(ohlcv, **kwargs)


def _ema(s: pl.Series, period: int) -> pl.Series:
    return s.ewm_mean(alpha=2.0 / (period + 1.0), adjust=False)


def _wilder(s: pl.Series, period: int) -> pl.Series:
    return s.ewm_mean(alpha=1.0 / period, adjust=False)


@indicator("sma", params={"period": 20}, display="overlay")
def sma(ohlcv: pl.DataFrame, period: int) -> pl.DataFrame:
    return pl.DataFrame({f"sma_{period}": ohlcv["close"].rolling_mean(window_size=period)})


@indicator("ema", params={"period": 20}, display="overlay")
def ema(ohlcv: pl.DataFrame, period: int) -> pl.DataFrame:
    return pl.DataFrame({f"ema_{period}": _ema(ohlcv["close"], period)})


@indicator("rsi", params={"period": 14}, display="pane")
def rsi(ohlcv: pl.DataFrame, period: int) -> pl.DataFrame:
    delta = ohlcv["close"].diff().fill_null(0.0)
    gain = _wilder(delta.clip(lower_bound=0.0), period)
    loss = _wilder((-delta).clip(lower_bound=0.0), period)
    return pl.DataFrame({f"rsi_{period}": 100.0 * gain / (gain + loss)})


@indicator("macd", params={"fast": 12, "slow": 26, "signal": 9}, display="pane")
def macd(ohlcv: pl.DataFrame, fast: int, slow: int, signal: int) -> pl.DataFrame:
    line = _ema(ohlcv["close"], fast) - _ema(ohlcv["close"], slow)
    sig = _ema(line, signal)
    return pl.DataFrame({"macd": line, "macd_signal": sig, "macd_hist": line - sig})


@indicator("bbands", params={"period": 20, "mult": 2.0}, display="overlay")
def bbands(ohlcv: pl.DataFrame, period: int, mult: float) -> pl.DataFrame:
    mid = ohlcv["close"].rolling_mean(window_size=period)
    sd = ohlcv["close"].rolling_std(window_size=period)
    return pl.DataFrame(
        {
            f"bb_mid_{period}": mid,
            f"bb_upper_{period}": mid + mult * sd,
            f"bb_lower_{period}": mid - mult * sd,
        }
    )


@indicator("vwap", params={}, display="overlay")
def vwap(ohlcv: pl.DataFrame) -> pl.DataFrame:
    tp = (ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 3.0
    pv = (tp * ohlcv["volume"]).cum_sum()
    return pl.DataFrame({"vwap": pv / ohlcv["volume"].cum_sum()})


@indicator("atr", params={"period": 14}, display="pane")
def atr(ohlcv: pl.DataFrame, period: int) -> pl.DataFrame:
    prev_close = ohlcv["close"].shift(1)
    tr = pl.DataFrame(
        {
            "a": ohlcv["high"] - ohlcv["low"],
            "b": (ohlcv["high"] - prev_close).abs(),
            "c": (ohlcv["low"] - prev_close).abs(),
        }
    ).select(pl.max_horizontal("a", "b", "c").alias("tr"))["tr"]
    return pl.DataFrame({f"atr_{period}": _wilder(tr, period)})
