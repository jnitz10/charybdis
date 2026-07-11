from __future__ import annotations

import polars as pl
import pytest
from fastapi.testclient import TestClient

from charybdis.console import datasets
from charybdis.console.server import create_app


def test_list_datasets(console_data_dir):
    names = {d["name"] for d in datasets.list_datasets()}
    assert "study3_candles_1h" in names
    assert "study3_sc_backtest" in names
    entry = next(d for d in datasets.list_datasets() if d["name"] == "study3_candles_1h")
    assert entry["columns"] == 12
    assert entry["size_bytes"] > 0


def test_dataset_path_rejects_traversal(console_data_dir):
    with pytest.raises(ValueError):
        datasets.dataset_path("../evil")
    with pytest.raises(ValueError):
        datasets.dataset_path("a/b")


def test_scan_dataset_missing_raises(console_data_dir):
    with pytest.raises(FileNotFoundError):
        datasets.scan_dataset("nope")


def test_scan_dataset_reads(console_data_dir):
    df = datasets.scan_dataset("study3_candles_1h").collect()
    assert df.height == 120
    assert "close" in df.columns


def test_cached_payload_reuses_until_mtime_changes(console_data_dir):
    calls = []

    def build():
        calls.append(1)
        return {"x": 1}

    assert datasets.cached_payload("k", "study3_candles_1h", build) == {"x": 1}
    assert datasets.cached_payload("k", "study3_candles_1h", build) == {"x": 1}
    assert len(calls) == 1


def test_health_and_datasets_endpoints(console_data_dir):
    client = TestClient(create_app())
    assert client.get("/api/health").json() == {"status": "ok"}
    body = client.get("/api/datasets").json()
    assert any(d["name"] == "study1_fills_l2" for d in body)


def test_datasets_endpoint_empty_when_dir_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARYBDIS_DATA_DIR", str(tmp_path / "absent"))
    client = TestClient(create_app())
    assert client.get("/api/datasets").json() == []
