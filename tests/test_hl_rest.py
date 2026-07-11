from __future__ import annotations

import json
import os
import re
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import numpy as np
import polars as pl
import pytest

from charybdis.hl_rest import HyperliquidInfo, candle_snapshot, funding_history


START_MS = 1_767_225_600_000


def test_funding_history_paginates_deduplicates_and_guards_cursor(tmp_path):
    calls: list[dict[str, object]] = []
    first_page = [
        {
            "coin": "xyz:TEST",
            "time": START_MS + index * 3_600_000,
            "fundingRate": "0.0001",
            "premium": "0.0002",
        }
        for index in range(500)
    ]
    second_page = [
        first_page[-1],
        {
            "coin": "xyz:TEST",
            "time": START_MS + 500 * 3_600_000,
            "fundingRate": "0.0003",
            "premium": "0.0004",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json=first_page if len(calls) == 1 else second_page)

    client = HyperliquidInfo(
        cache_dir=tmp_path,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        requests_per_second=2,
    )
    frame = client.funding_history("xyz:TEST", START_MS)

    assert frame.height == 501
    assert frame.columns == [
        "market",
        "time_ms",
        "time_exchange",
        "funding_rate",
        "premium",
    ]
    assert frame.schema["time_ms"] == pl.Int64
    assert frame.schema["funding_rate"] == pl.Float64
    assert frame.schema["premium"] == pl.Float64
    assert calls[1]["startTime"] == first_page[-1]["time"] + 1

    stuck_page = [{**first_page[0], "time": START_MS - 1} for _ in range(500)]
    stuck = HyperliquidInfo(
        cache_dir=tmp_path / "stuck",
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=stuck_page)
            )
        ),
        requests_per_second=2,
    )
    with pytest.raises(RuntimeError, match="non-advancing funding cursor"):
        stuck.funding_history("xyz:TEST", START_MS)


def test_disk_cache_records_timestamp_and_avoids_second_network_call(tmp_path):
    network_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal network_calls
        network_calls += 1
        return httpx.Response(200, json=[{"name": "xyz"}, None])

    client = HyperliquidInfo(
        cache_dir=tmp_path,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        requests_per_second=2,
    )

    assert client.perp_dexs() == ["xyz"]
    assert client.perp_dexs() == ["xyz"]
    assert network_calls == 1
    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1
    cached = json.loads(cache_files[0].read_text())
    assert cached["payload"] == [{"name": "xyz"}, None]
    assert cached["fetched_at_utc"].endswith("+00:00")


def test_cache_atomic_write_uses_unique_pid_uuid_temp_name(tmp_path, monkeypatch):
    temporary_names: list[str] = []
    original_replace = Path.replace

    def recording_replace(source: Path, target: Path) -> Path:
        temporary_names.append(source.name)
        return original_replace(source, target)

    monkeypatch.setattr(Path, "replace", recording_replace)
    client = HyperliquidInfo(
        cache_dir=tmp_path,
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=[{"name": "xyz"}])
            )
        ),
        requests_per_second=2,
    )

    assert client.perp_dexs() == ["xyz"]
    assert len(temporary_names) == 1
    assert re.fullmatch(
        rf"[0-9a-f]{{64}}\.json\.{os.getpid()}\.[0-9a-f]{{32}}\.part",
        temporary_names[0],
    )


@pytest.mark.parametrize("payload", [[], {"error": "temporarily unavailable"}])
def test_degraded_http_200_is_not_cached_and_is_refetched(tmp_path, payload):
    network_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal network_calls
        network_calls += 1
        return httpx.Response(200, json=payload)

    client = HyperliquidInfo(
        cache_dir=tmp_path,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        requests_per_second=2,
    )
    body = {"type": "fundingHistory", "coin": "xyz:TEST", "startTime": START_MS}

    assert client._post(body) == payload
    assert client._post(body) == payload
    assert network_calls == 2
    assert list(tmp_path.glob("*.json")) == []


def test_epoch_trap_and_invalid_window_raise_before_network(tmp_path):
    def fail_if_called(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"network should not be called: {request}")

    client = HyperliquidInfo(
        cache_dir=tmp_path,
        http_client=httpx.Client(transport=httpx.MockTransport(fail_if_called)),
        requests_per_second=2,
    )

    with pytest.raises(ValueError, match="sane 2026"):
        client.funding_history("xyz:TEST", 1_735_689_600_000)
    with pytest.raises(ValueError, match="end_ms"):
        client.funding_history("xyz:TEST", START_MS + 1, end_ms=START_MS)
    with pytest.raises(ValueError, match="sane 2026"):
        client.candle_snapshot(
            "xyz:TEST", "1h", START_MS, int(datetime.now(UTC).timestamp() * 1000) + 1
        )


def test_numpy_integer_timestamps_serialize_through_public_apis(tmp_path):
    funding_calls: list[dict[str, object]] = []
    candle_calls: list[dict[str, object]] = []

    def funding_handler(request: httpx.Request) -> httpx.Response:
        funding_calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=[
                {
                    "coin": "xyz:TEST",
                    "time": START_MS,
                    "fundingRate": "0.0001",
                    "premium": "0.0002",
                }
            ],
        )

    def candle_handler(request: httpx.Request) -> httpx.Response:
        candle_calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=[
                {
                    "t": START_MS,
                    "T": START_MS + 3_599_999,
                    "s": "xyz:TEST",
                    "i": "1h",
                    "o": "10",
                    "h": "12",
                    "l": "9",
                    "c": "11",
                    "v": "123.5",
                    "n": 7,
                }
            ],
        )

    funding_client = HyperliquidInfo(
        cache_dir=tmp_path / "funding",
        http_client=httpx.Client(transport=httpx.MockTransport(funding_handler)),
        requests_per_second=2,
    )
    candle_client = HyperliquidInfo(
        cache_dir=tmp_path / "candles",
        http_client=httpx.Client(transport=httpx.MockTransport(candle_handler)),
        requests_per_second=2,
    )
    start_ms = np.int64(START_MS)
    end_ms = np.int64(START_MS + 3_600_000)

    assert funding_client.funding_history("xyz:TEST", start_ms, end_ms=end_ms).height == 1
    assert candle_client.candle_snapshot("xyz:TEST", "1h", start_ms, end_ms).height == 1
    assert funding_calls[0]["startTime"] == START_MS
    assert candle_calls[0]["req"]["endTime"] == START_MS + 3_600_000


def test_funding_history_allows_missing_premium_but_requires_funding_rate(tmp_path):
    responses = [
        [
            {
                "coin": "xyz:TEST",
                "time": START_MS,
                "fundingRate": "0.0001",
            },
            {
                "coin": "xyz:TEST",
                "time": START_MS + 1,
                "fundingRate": "0.0002",
                "premium": None,
            },
        ],
        [{"coin": "xyz:TEST", "time": START_MS}],
    ]
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        response = httpx.Response(200, json=responses[calls])
        calls += 1
        return response

    client = HyperliquidInfo(
        cache_dir=tmp_path,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        requests_per_second=2,
    )

    frame = client.funding_history("xyz:TEST", START_MS, refresh=True)
    assert frame.get_column("premium").to_list() == [None, None]
    with pytest.raises(KeyError, match="fundingRate"):
        client.funding_history("xyz:TEST", START_MS, refresh=True)


def test_candle_snapshot_continues_after_short_page(tmp_path):
    calls: list[dict[str, object]] = []

    def candle(at: int, close: str) -> dict[str, object]:
        return {
            "t": at,
            "T": at + 3_599_999,
            "s": "xyz:TEST",
            "i": "1h",
            "o": "10",
            "h": "12",
            "l": "9",
            "c": close,
            "v": "123.5",
            "n": 7,
        }

    pages = [
        [candle(START_MS, "11"), candle(START_MS + 3_600_000, "11.5")],
        [
            candle(START_MS + 3_600_000, "11.5"),
            candle(START_MS + 2 * 3_600_000, "12"),
            candle(START_MS + 3 * 3_600_000, "12.5"),
        ],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=pages[len(calls) - 1])

    client = HyperliquidInfo(
        cache_dir=tmp_path,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        requests_per_second=2,
    )
    frame = client.candle_snapshot(
        "xyz:TEST", "1h", START_MS, START_MS + 4 * 3_600_000
    )

    assert frame.height == 4
    assert frame.get_column("trade_count").to_list() == [7, 7, 7, 7]
    assert frame.get_column("volume").dtype.is_float()
    assert len(calls) == 2
    assert calls[1]["req"]["startTime"] == START_MS + 2 * 3_600_000


def test_candle_snapshot_continues_after_duplicate_padded_page(tmp_path):
    calls: list[dict[str, object]] = []
    step_ms = 3_600_000

    def candle(index: int) -> dict[str, object]:
        at = START_MS + index * step_ms
        return {
            "t": at,
            "T": at + step_ms - 1,
            "s": "xyz:TEST",
            "i": "1h",
            "o": "10",
            "h": "12",
            "l": "9",
            "c": "11",
            "v": "123.5",
            "n": 7,
        }

    pages = [
        [candle(0), candle(1), candle(2), candle(2)],
        [candle(3)],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=pages[len(calls) - 1])

    client = HyperliquidInfo(
        cache_dir=tmp_path,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        requests_per_second=2,
    )
    frame = client.candle_snapshot(
        "xyz:TEST", "1h", START_MS, START_MS + 4 * step_ms
    )

    assert frame.get_column("open_time_ms").to_list() == [
        START_MS + index * step_ms for index in range(4)
    ]
    assert calls == [
        {
            "type": "candleSnapshot",
            "req": {
                "coin": "xyz:TEST",
                "interval": "1h",
                "startTime": START_MS,
                "endTime": START_MS + 4 * step_ms,
            },
        },
        {
            "type": "candleSnapshot",
            "req": {
                "coin": "xyz:TEST",
                "interval": "1h",
                "startTime": START_MS + 3 * step_ms,
                "endTime": START_MS + 4 * step_ms,
            },
        },
    ]


@pytest.mark.skipif(os.environ.get("HL_LIVE") != "1", reason="set HL_LIVE=1")
def test_live_skhx_history_and_daily_candle_inception():
    now_ms = int(datetime.now(UTC).timestamp() * 1000)

    funding = funding_history("xyz:SKHX", START_MS)
    candles = candle_snapshot("xyz:SKHX", "1d", START_MS, now_ms)

    assert funding.height >= 1_978
    assert candles.height > 0
    assert candles.item(0, "time_open").date() <= date(2026, 2, 19)
