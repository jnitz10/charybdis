from __future__ import annotations

from fastapi.testclient import TestClient

from charybdis.console.server import create_app


def _client():
    return TestClient(create_app())


def test_findings_endpoint(console_data_dir):
    body = _client().get("/api/findings").json()
    ids = [s["id"] for s in body["studies"]]
    assert ids == ["study1", "study2", "study3"]
    s3 = body["studies"][2]
    assert s3["verdict"]
    assert s3["numbers"]
    assert s3["page"].startswith("/")


def test_study1_markout(console_data_dir):
    body = _client().get("/api/study1/markout").json()
    assert body["horizons"] == ["1s", "30s", "2m"]  # sorted by seconds, not schema order
    assert set(body["segments"]) == {"RTH", "off-hours"}
    assert set(body["markets"]) == {"xyz:AAA", "km:BBB"}
    cell = next(
        c
        for c in body["cells"]
        if c["market"] == "xyz:AAA" and c["segment"] == "RTH" and c["horizon"] == "1s"
    )
    # fixture: 10 rows, one stale_1s row excluded -> n=9, mean of -1.0..-1.8
    assert cell["n"] == 9
    assert abs(cell["mean_bps"] - (-1.4)) < 1e-9


def test_study1_markout_absent_404(console_data_dir):
    (console_data_dir / "study1_fills_l2.parquet").unlink()
    assert _client().get("/api/study1/markout").status_code == 404
