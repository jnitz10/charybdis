from __future__ import annotations

from fastapi.testclient import TestClient

from charybdis.console.server import create_app


def _client():
    return TestClient(create_app())


def test_indicators_endpoint(console_data_dir):
    body = _client().get("/api/indicators").json()
    names = {m["name"] for m in body}
    assert {"sma", "ema", "rsi", "macd", "bbands", "vwap", "atr"} <= names


def test_sources_lists_only_present(console_data_dir):
    body = _client().get("/api/candles/sources").json()
    ids = {s["id"] for s in body}
    assert ids == {"study3_1h"}  # fixture has no 1d file
    src = body[0]
    assert src["interval"] == "1h"
    assert src["markets"] == ["km:BBB", "xyz:AAA"]


def test_candles_payload(console_data_dir):
    r = _client().get("/api/candles?source=study3_1h&market=xyz%3AAAA&ind=ema:5,rsi:14").json()
    assert r["market"] == "xyz:AAA"
    assert len(r["time"]) == 60
    assert len(r["close"]) == 60
    assert r["time"] == sorted(r["time"])
    inds = {i["id"]: i for i in r["indicators"]}
    assert inds["ema:5"]["display"] == "overlay"
    assert "ema_5" in inds["ema:5"]["series"]
    assert len(inds["ema:5"]["series"]["ema_5"]) == 60
    assert inds["rsi:14"]["display"] == "pane"


def test_candles_unknown_source_404(console_data_dir):
    assert _client().get("/api/candles?source=nope&market=x").status_code == 404


def test_candles_unknown_market_404(console_data_dir):
    assert (
        _client().get("/api/candles?source=study3_1h&market=xyz%3AZZZ").status_code == 404
    )


def test_candles_bad_indicator_400(console_data_dir):
    r = _client().get("/api/candles?source=study3_1h&market=xyz%3AAAA&ind=nope:1")
    assert r.status_code == 400


def test_candles_bad_indicator_named_no_rows_400(console_data_dir):
    r = _client().get("/api/candles?source=study3_1h&market=xyz%3AAAA&ind=no%20rows")
    assert r.status_code == 400


def test_candles_nonpositive_indicator_param_400(console_data_dir):
    r = _client().get("/api/candles?source=study3_1h&market=xyz%3AAAA&ind=sma:-3")
    assert r.status_code == 400
    r = _client().get("/api/candles?source=study3_1h&market=xyz%3AAAA&ind=rsi:0")
    assert r.status_code == 400
