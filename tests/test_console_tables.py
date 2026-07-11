from __future__ import annotations

import math

from fastapi.testclient import TestClient

from charybdis.console.server import create_app
from charybdis.console.tables import json_value


def _client():
    return TestClient(create_app())


def test_schema(console_data_dir):
    body = _client().get("/api/datasets/study3_candles_1h/schema").json()
    assert body["name"] == "study3_candles_1h"
    cols = {c["name"]: c["dtype"] for c in body["columns"]}
    assert cols["close"] == "Float64"
    assert cols["market"] == "String"


def test_schema_missing_dataset_404(console_data_dir):
    r = _client().get("/api/datasets/nope/schema")
    assert r.status_code == 404
    assert "not present" in r.json()["detail"]


def test_rows_pagination(console_data_dir):
    r = _client().get("/api/datasets/study3_candles_1h/rows?page=2&page_size=50").json()
    assert r["total"] == 120
    assert r["page"] == 2
    assert len(r["rows"]) == 50
    assert r["columns"][0] == "dex"


def test_rows_filter_and_sort(console_data_dir):
    r = _client().get(
        "/api/datasets/study3_candles_1h/rows"
        "?filter=market:eq:xyz%3AAAA&sort=close&order=desc&page_size=5"
    ).json()
    assert r["total"] == 60
    closes = [row[r["columns"].index("close")] for row in r["rows"]]
    assert closes == sorted(closes, reverse=True)


def test_rows_contains_filter(console_data_dir):
    r = _client().get("/api/datasets/study3_candles_1h/rows?filter=market:contains:BBB").json()
    assert r["total"] == 60


def test_rows_numeric_filter(console_data_dir):
    r = _client().get("/api/datasets/study3_candles_1h/rows?filter=v:gt:50").json()
    assert 0 < r["total"] < 120


def test_rows_bad_filter_column_400(console_data_dir):
    r = _client().get("/api/datasets/study3_candles_1h/rows?filter=nope:eq:1")
    assert r.status_code == 400


def test_json_value():
    from datetime import datetime

    assert json_value(datetime(2026, 6, 1)) == "2026-06-01T00:00:00"
    assert json_value(math.nan) is None
    assert json_value(math.inf) is None
    assert json_value([math.nan, 1.0]) == [None, 1.0]
    assert json_value("x") == "x"
