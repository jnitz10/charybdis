from __future__ import annotations

import polars as pl
import pytest

from charybdis.console import indicators


def _ohlcv(closes: list[float], highs=None, lows=None, vols=None) -> pl.DataFrame:
    n = len(closes)
    return pl.DataFrame(
        {
            "open": closes,
            "high": highs or [c + 1 for c in closes],
            "low": lows or [c - 1 for c in closes],
            "close": closes,
            "volume": vols or [1.0] * n,
        }
    )


def test_registry_contents():
    assert set(indicators.REGISTRY) == {"sma", "ema", "rsi", "macd", "bbands", "vwap", "atr"}
    assert indicators.REGISTRY["ema"].display == "overlay"
    assert indicators.REGISTRY["rsi"].display == "pane"


def test_sma_golden():
    _, out = indicators.compute("sma:3", _ohlcv([1, 2, 3, 4, 5]))
    assert out["sma_3"].to_list() == [None, None, 2.0, 3.0, 4.0]


def test_ema_golden():
    # period 3 -> alpha 0.5, adjust=False: 1, 1.5, 2.25, 3.125, 4.0625
    _, out = indicators.compute("ema:3", _ohlcv([1, 2, 3, 4, 5]))
    assert out["ema_3"].to_list() == pytest.approx([1.0, 1.5, 2.25, 3.125, 4.0625])


def test_rsi_bounds():
    up = [float(i) for i in range(1, 30)]
    _, out = indicators.compute("rsi:14", _ohlcv(up))
    assert out["rsi_14"][-1] == pytest.approx(100.0)
    down = [float(30 - i) for i in range(1, 30)]
    _, out = indicators.compute("rsi:14", _ohlcv(down))
    assert out["rsi_14"][-1] == pytest.approx(0.0)


def test_macd_constant_is_zero():
    _, out = indicators.compute("macd", _ohlcv([5.0] * 60))
    assert out["macd"][-1] == pytest.approx(0.0)
    assert out["macd_signal"][-1] == pytest.approx(0.0)
    assert out["macd_hist"][-1] == pytest.approx(0.0)
    assert set(out.columns) == {"macd", "macd_signal", "macd_hist"}


def test_bbands_constant_collapses():
    _, out = indicators.compute("bbands:5:2", _ohlcv([7.0] * 10))
    assert out["bb_mid_5"][-1] == pytest.approx(7.0)
    assert out["bb_upper_5"][-1] == pytest.approx(7.0)
    assert out["bb_lower_5"][-1] == pytest.approx(7.0)


def test_vwap_equal_volume_is_cumulative_mean_of_typical():
    df = _ohlcv([2.0, 4.0], highs=[3.0, 5.0], lows=[1.0, 3.0])
    # typical prices: 2.0 and 4.0 -> vwap: 2.0, 3.0
    _, out = indicators.compute("vwap", df)
    assert out["vwap"].to_list() == pytest.approx([2.0, 3.0])


def test_atr_golden():
    df = _ohlcv([9.5, 10.5], highs=[10.0, 11.0], lows=[9.0, 10.0])
    # TR: [1.0, max(1.0, |11-9.5|, |10-9.5|)=1.5]; alpha=0.5 -> [1.0, 1.25]
    _, out = indicators.compute("atr:2", df)
    assert out["atr_2"].to_list() == pytest.approx([1.0, 1.25])


def test_compute_parsing_errors():
    with pytest.raises(ValueError):
        indicators.compute("nope:3", _ohlcv([1, 2, 3]))
    with pytest.raises(ValueError):
        indicators.compute("sma:abc", _ohlcv([1, 2, 3]))


def test_registry_meta_shape():
    meta = {m["name"]: m for m in indicators.registry_meta()}
    assert meta["macd"]["params"] == {"fast": 12, "slow": 26, "signal": 9}
    assert meta["vwap"]["params"] == {}


def test_registry_meta_returns_copies():
    meta = {m["name"]: m for m in indicators.registry_meta()}
    meta["macd"]["params"]["fast"] = 999
    assert indicators.REGISTRY["macd"].params["fast"] == 12
