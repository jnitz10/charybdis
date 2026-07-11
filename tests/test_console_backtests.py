from __future__ import annotations

from fastapi.testclient import TestClient

from charybdis.console.server import create_app


def _client():
    return TestClient(create_app())


def test_list_backtests(console_data_dir):
    body = _client().get("/api/backtests").json()
    ids = {b["id"] for b in body}
    assert "study3-carry:short-only-daily" in ids
    entry = body[0]
    assert entry["source"] == "study3-carry"
    assert entry["strategy"] == "short-only-daily"


def test_get_backtest_detail(console_data_dir):
    r = _client().get("/api/backtests/study3-carry:short-only-daily").json()
    assert r["stats"]["periods"] == 40
    assert len(r["equity"]) == 40
    # equity is the cumulative sum of period returns
    assert r["equity"][-1]["v"] != 0
    # drawdown is <= 0 everywhere
    assert all(p["v"] <= 1e-12 for p in r["drawdown"])
    assert r["stats"]["max_drawdown"] <= 0
    # monthly buckets cover jun+jul 2026 (40 daily periods from 2026-06-01)
    yms = [m["ym"] for m in r["monthly"]]
    assert yms == ["2026-06", "2026-07"]
    # sc_summary row is merged
    assert r["summary"]["sharpe"] == -2.654


def test_get_backtest_unknown_404(console_data_dir):
    assert _client().get("/api/backtests/nope:x").status_code == 404


def test_backtests_empty_when_dataset_absent(console_data_dir):
    (console_data_dir / "study3_sc_backtest.parquet").unlink()
    assert _client().get("/api/backtests").json() == []
