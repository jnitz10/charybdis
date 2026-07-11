"""Raw CoinAPI archive browsing + raw-trades candles + expanded dataset discovery."""
from __future__ import annotations

from fastapi.testclient import TestClient

from charybdis.console.server import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_raw_feeds_empty_without_archive(console_data_dir):
    assert _client().get("/api/raw/feeds").json() == []


def test_raw_feeds_summary(raw_data_dir):
    feeds = {f["feed"]: f for f in _client().get("/api/raw/feeds").json()}
    assert set(feeds) == {"TRADES", "HLSYSTEMEVENTS", "HLORACLEPRICES"}
    t = feeds["TRADES"]
    assert t["partitions"] == 3
    assert t["files"] == 3
    assert t["eras"] == ["l2", "l4"]
    assert t["first_day"] == "2026-03-11"
    assert t["last_day"] == "2026-03-12"
    assert t["size_bytes"] > 0
    assert feeds["HLSYSTEMEVENTS"]["markets"] == 1


def test_raw_markets(raw_data_dir):
    r = _client().get("/api/raw/markets", params={"feed": "TRADES"})
    assert r.status_code == 200
    (m,) = r.json()
    assert m["market"] == "km:US500"
    assert m["files"] == 3
    assert m["eras"] == ["l2", "l4"]
    sys_markets = _client().get("/api/raw/markets", params={"feed": "HLSYSTEMEVENTS"}).json()
    assert [m["market"] for m in sys_markets] == ["all"]


def test_raw_markets_unknown_feed_404(raw_data_dir):
    assert _client().get("/api/raw/markets", params={"feed": "NOPE"}).status_code == 404


def test_raw_feed_name_validation(raw_data_dir):
    r = _client().get("/api/raw/markets", params={"feed": "../reports"})
    assert r.status_code == 400


def test_raw_files_filters(raw_data_dir):
    c = _client()
    all_files = c.get("/api/raw/files", params={"feed": "TRADES"}).json()
    assert len(all_files) == 3
    assert [f["partition"] for f in all_files] == ["D-20260311", "D-20260312", "D-2026031211"]
    one = c.get(
        "/api/raw/files", params={"feed": "TRADES", "partition": "D-2026031211"}
    ).json()
    assert len(one) == 1
    assert one[0]["era"] == "l4"
    assert one[0]["day"] == "2026-03-12"


def test_raw_preview_l2_trades(raw_data_dir):
    r = _client().get(
        "/api/raw/preview",
        params={"feed": "TRADES", "partition": "D-20260311", "market": "km:US500"},
    )
    assert r.status_code == 200
    p = r.json()
    assert p["total"] == 3
    assert p["era"] == "l2"
    cols = {c["name"]: c["dtype"] for c in p["columns"]}
    assert cols["price"] == "Float64"
    assert cols["time_exchange"].startswith("Datetime")
    row = dict(zip([c["name"] for c in p["columns"]], p["rows"][0]))
    assert row["price"] == 100.0
    assert row["time_exchange"].startswith("2026-03-11T10:00:00")


def test_raw_preview_whole_exchange_file(raw_data_dir):
    p = _client().get(
        "/api/raw/preview",
        params={"feed": "HLSYSTEMEVENTS", "partition": "D-2026031211"},
    ).json()
    assert p["market"] == "all"
    assert p["total"] == 1
    names = [c["name"] for c in p["columns"]]
    assert "json_payload" in names


def test_raw_preview_missing_404(raw_data_dir):
    r = _client().get(
        "/api/raw/preview",
        params={"feed": "TRADES", "partition": "D-19990101", "market": "km:US500"},
    )
    assert r.status_code == 404


def test_candle_sources_include_raw(raw_data_dir):
    sources = {s["id"]: s for s in _client().get("/api/candles/sources").json()}
    assert "raw_trades_1h" in sources
    assert sources["raw_trades_1h"]["markets"] == ["km:US500"]
    assert "study3_1h" in sources  # parquet sources still listed


def test_raw_trade_candles_dedup_eras(raw_data_dir):
    r = _client().get(
        "/api/candles", params={"source": "raw_trades_1h", "market": "km:US500"}
    )
    assert r.status_code == 200
    p = r.json()
    # day 1: one 10:00 bar from L2. day 2 is covered by both eras -> L4 only,
    # so its bar is the 11:00 L4 hour and the 500.0 L2 prints are dropped.
    assert len(p["time"]) == 2
    assert p["open"] == [100.0, 102.0]
    assert p["high"] == [101.0, 103.0]
    assert p["close"] == [99.0, 103.0]
    assert p["volume"] == [1.5, 4.0]
    assert p["interval"] == "1h"


def test_raw_trade_candles_with_indicator(raw_data_dir):
    r = _client().get(
        "/api/candles",
        params={"source": "raw_trades_1m", "market": "km:US500", "ind": "sma:2"},
    )
    assert r.status_code == 200
    assert r.json()["indicators"][0]["name"] == "sma"


def test_raw_trade_candles_unknown_market_404(raw_data_dir):
    r = _client().get(
        "/api/candles", params={"source": "raw_trades_1h", "market": "xyz:NOPE"}
    )
    assert r.status_code == 404


def test_raw_trade_candles_salvage_corrupt_gzip(raw_data_dir):
    import gzip

    from tests.conftest import l2_trades_csv

    # a truncated gzip on its own L2-only day: candles survive and warn
    payload = gzip.compress(l2_trades_csv("2026-03-10", [42.0]).encode())
    bad = (
        raw_data_dir
        / "T-TRADES/D-20260310/E-HYPERLIQUID"
        / "IDDI-1+SC-HYPERLIQUID_DPERP_KM_US500_USDC+S-KM__003AUS500.csv.gz"
    )
    bad.parent.mkdir(parents=True)
    bad.write_bytes(payload[: len(payload) // 2])
    r = _client().get(
        "/api/candles", params={"source": "raw_trades_1h", "market": "km:US500"}
    )
    assert r.status_code == 200
    p = r.json()
    assert len(p["time"]) == 2  # the good days still produce their bars
    assert len(p["warnings"]) == 1
    assert "corrupt" in p["warnings"][0]

    preview = _client().get(
        "/api/raw/preview",
        params={"feed": "TRADES", "partition": "D-20260310", "market": "km:US500"},
    )
    assert preview.status_code == 500
    assert "unreadable" in preview.json()["detail"]


def test_datasets_include_loose_and_parts(raw_data_dir):
    ds = {d["name"]: d for d in _client().get("/api/datasets").json()}
    assert ds["loose_funding"]["kind"] == "table"
    assert ds["parts_ds"]["kind"] == "parts"
    assert ds["parts_ds"]["files"] == 2
    assert ds["study3_candles_1h"]["kind"] == "table"


def test_parts_dataset_rows_and_schema(raw_data_dir):
    c = _client()
    schema = c.get("/api/datasets/parts_ds/schema").json()
    assert [col["name"] for col in schema["columns"]] == ["market", "x"]
    rows = c.get("/api/datasets/parts_ds/rows", params={"sort": "x"}).json()
    assert rows["total"] == 2
    assert rows["rows"][0][0] == "a"


def test_loose_dataset_rows(raw_data_dir):
    rows = _client().get("/api/datasets/loose_funding/rows").json()
    assert rows["total"] == 1
    assert rows["rows"][0][0] == "GOLD"
