"""Cached, rate-limited client for Hyperliquid's public ``/info`` endpoint.

Funding history is normalized to one canonical schema: ``market`` (``dex:COIN``),
``time_ms`` (Int64), ``time_exchange`` (naive UTC Datetime), ``funding_rate``
(Float64), and ``premium`` (Float64). Times are unmodified settlement times.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

import httpx
import polars as pl


INFO_URL = "https://api.hyperliquid.xyz/info"
EARLIEST_SANE_MS = 1_767_225_600_000  # 2026-01-01T00:00:00Z
FUNDING_PAGE_SIZE = 500
CANDLE_PAGE_SIZE = 5_000
INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}


class HyperliquidInfo:
    """HTTP-native Hyperliquid info client with polite request pacing."""

    def __init__(
        self,
        *,
        cache_dir: str | Path = "data/rest_cache",
        http_client: httpx.Client | None = None,
        requests_per_second: float = 1.0,
    ) -> None:
        if not 0 < requests_per_second <= 2:
            raise ValueError("requests_per_second must be in (0, 2]")
        self.cache_dir = Path(cache_dir)
        self.client = http_client or httpx.Client(timeout=30)
        self._owns_client = http_client is None
        self._request_interval = 1.0 / requests_per_second
        self._next_request_at = 0.0
        self._rate_lock = Lock()
        self.rest_calls = 0
        self.cache_hits = 0

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> HyperliquidInfo:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _wait_for_request_slot(self) -> None:
        with self._rate_lock:
            now = time.monotonic()
            delay = max(0.0, self._next_request_at - now)
            self._next_request_at = max(now, self._next_request_at) + self._request_interval
        if delay:
            time.sleep(delay)

    def _post(self, body: dict[str, Any], *, refresh: bool = False) -> Any:
        canonical_body = json.dumps(
            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        cache_path = self.cache_dir / f"{hashlib.sha256(canonical_body).hexdigest()}.json"
        if cache_path.exists() and not refresh:
            self.cache_hits += 1
            cached = json.loads(cache_path.read_text())
            return cached["payload"]

        backoff = 2.0
        for attempt in range(8):
            self._wait_for_request_slot()
            self.rest_calls += 1
            response = self.client.post(INFO_URL, json=body)
            if response.status_code not in {403, 429}:
                response.raise_for_status()
                payload = response.json()
                request_type = body.get("type")
                contains_error = isinstance(payload, dict) and "error" in payload
                if request_type in {"perpDexs", "fundingHistory", "candleSnapshot"}:
                    valid_shape = isinstance(payload, list)
                elif request_type == "metaAndAssetCtxs":
                    valid_shape = (
                        isinstance(payload, list)
                        and len(payload) == 2
                        and isinstance(payload[0], dict)
                        and isinstance(payload[1], list)
                    )
                else:
                    valid_shape = False
                cacheable = (
                    valid_shape
                    and not contains_error
                    and not (
                        request_type in {"fundingHistory", "candleSnapshot"}
                        and payload == []
                    )
                )
                if not cacheable:
                    return payload
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                record = {
                    "fetched_at_utc": datetime.now(UTC).isoformat(),
                    "request": body,
                    "payload": payload,
                }
                temporary = cache_path.parent / (
                    f"{cache_path.name}.{os.getpid()}.{uuid.uuid4().hex}.part"
                )
                temporary.write_text(
                    json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
                )
                temporary.replace(cache_path)
                return payload
            if attempt == 7:
                response.raise_for_status()
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
        raise AssertionError("unreachable retry loop")

    def perp_dexs(self, *, refresh: bool = False) -> list[str]:
        """Return the currently registered HIP-3 perp DEX names."""

        payload = self._post({"type": "perpDexs"}, refresh=refresh)
        if not isinstance(payload, list):
            raise RuntimeError(f"unexpected perpDexs payload: {payload!r}")
        return [str(record["name"]) for record in payload if record]

    def meta_and_asset_ctxs(
        self, dex: str | None = None, *, refresh: bool = False
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Return a metadata/context snapshot for the main or one HIP-3 DEX."""

        body = {"type": "metaAndAssetCtxs"}
        if dex is not None:
            body["dex"] = dex
        payload = self._post(body, refresh=refresh)
        if not isinstance(payload, list) or len(payload) != 2:
            raise RuntimeError(f"unexpected metaAndAssetCtxs payload for {dex}: {payload!r}")
        metadata, contexts = payload
        if not isinstance(metadata, dict) or not isinstance(contexts, list):
            raise RuntimeError(f"unexpected metaAndAssetCtxs payload for {dex}: {payload!r}")
        return metadata, contexts

    @staticmethod
    def _validate_start_ms(start_ms: int) -> None:
        start_ms = int(start_ms)
        now_ms = int(datetime.now(UTC).timestamp() * 1000)
        if not EARLIEST_SANE_MS <= start_ms <= now_ms:
            raise ValueError(
                f"start_ms {start_ms} is outside the sane 2026..now millisecond range"
            )

    def funding_history(
        self,
        coin: str,
        start_ms: int,
        *,
        end_ms: int | None = None,
        refresh: bool = False,
    ) -> pl.DataFrame:
        """Return raw settlements, paginating by the maximum returned timestamp."""

        start_ms = int(start_ms)
        end_ms = int(end_ms) if end_ms is not None else None
        self._validate_start_ms(start_ms)
        if end_ms is not None:
            self._validate_start_ms(end_ms)
        if end_ms is not None and end_ms <= start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        cursor = start_ms
        raw_rows: list[dict[str, Any]] = []
        while end_ms is None or cursor < end_ms:
            page = self._post(
                {"type": "fundingHistory", "coin": coin, "startTime": cursor},
                refresh=refresh,
            )
            if not isinstance(page, list):
                raise RuntimeError(f"unexpected funding payload for {coin}: {page!r}")
            if not page:
                break
            raw_rows.extend(
                row for row in page if end_ms is None or int(row["time"]) < end_ms
            )
            maximum = max(int(row["time"]) for row in page)
            next_cursor = maximum + 1
            if next_cursor <= cursor:
                raise RuntimeError(f"non-advancing funding cursor for {coin}")
            cursor = next_cursor
            if len(page) < FUNDING_PAGE_SIZE or (end_ms is not None and maximum >= end_ms):
                break

        unique = {
            (str(row.get("coin", coin)), int(row["time"])): row for row in raw_rows
        }
        normalized = [
            {
                "market": market,
                "time_ms": time_ms,
                "time_exchange": datetime.fromtimestamp(time_ms / 1000, UTC).replace(
                    tzinfo=None
                ),
                "funding_rate": float(row["fundingRate"]),
                "premium": (
                    float(row["premium"]) if row.get("premium") is not None else None
                ),
            }
            for (market, time_ms), row in unique.items()
        ]
        schema = {
            "market": pl.String,
            "time_ms": pl.Int64,
            "time_exchange": pl.Datetime("us"),
            "funding_rate": pl.Float64,
            "premium": pl.Float64,
        }
        return pl.DataFrame(normalized, schema=schema).sort(["market", "time_ms"])

    def candle_snapshot(
        self,
        coin: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        *,
        refresh: bool = False,
    ) -> pl.DataFrame:
        """Return typed OHLCV candles over the complete requested half-open span."""

        start_ms = int(start_ms)
        end_ms = int(end_ms)
        self._validate_start_ms(start_ms)
        self._validate_start_ms(end_ms)
        if end_ms <= start_ms:
            raise ValueError("end_ms must be greater than start_ms")
        try:
            step_ms = INTERVAL_MS[interval]
        except KeyError as exc:
            raise ValueError(f"unsupported candle interval: {interval}") from exc

        cursor = start_ms
        raw_rows: list[dict[str, Any]] = []
        while cursor < end_ms:
            request_end = min(end_ms, cursor + CANDLE_PAGE_SIZE * step_ms)
            page = self._post(
                {
                    "type": "candleSnapshot",
                    "req": {
                        "coin": coin,
                        "interval": interval,
                        "startTime": cursor,
                        "endTime": request_end,
                    },
                },
                refresh=refresh,
            )
            if not isinstance(page, list):
                raise RuntimeError(f"unexpected candle payload for {coin}: {page!r}")
            raw_rows.extend(
                row for row in page if start_ms <= int(row["t"]) < end_ms
            )
            if not page:
                cursor = request_end
                continue

            maximum = max(int(row["t"]) for row in page)
            next_cursor = maximum + step_ms
            if next_cursor <= cursor:
                raise RuntimeError(f"non-advancing candle cursor for {coin} {interval}")
            cursor = next_cursor

        unique = {int(row["t"]): row for row in raw_rows}
        normalized = [
            {
                "market": str(row.get("s", coin)),
                "interval": str(row.get("i", interval)),
                "open_time_ms": open_ms,
                "close_time_ms": int(row["T"]),
                "time_open": datetime.fromtimestamp(open_ms / 1000, UTC).replace(
                    tzinfo=None
                ),
                "open": float(row["o"]),
                "high": float(row["h"]),
                "low": float(row["l"]),
                "close": float(row["c"]),
                "volume": float(row["v"]),
                "trade_count": int(row["n"]),
            }
            for open_ms, row in unique.items()
        ]
        schema = {
            "market": pl.String,
            "interval": pl.String,
            "open_time_ms": pl.Int64,
            "close_time_ms": pl.Int64,
            "time_open": pl.Datetime("us"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "trade_count": pl.Int64,
        }
        return pl.DataFrame(normalized, schema=schema).sort("open_time_ms")


_DEFAULT_API: HyperliquidInfo | None = None
_DEFAULT_API_LOCK = Lock()


def _default_api() -> HyperliquidInfo:
    global _DEFAULT_API
    with _DEFAULT_API_LOCK:
        if _DEFAULT_API is None:
            _DEFAULT_API = HyperliquidInfo()
        return _DEFAULT_API


def perp_dexs(*, refresh: bool = False) -> list[str]:
    """Fetch the registered HIP-3 DEX names using the shared disk cache."""

    return _default_api().perp_dexs(refresh=refresh)


def meta_and_asset_ctxs(
    dex: str | None = None, *, refresh: bool = False
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fetch a main- or HIP-3-DEX snapshot using the shared disk cache."""

    return _default_api().meta_and_asset_ctxs(dex, refresh=refresh)


def funding_history(
    coin: str,
    start_ms: int,
    *,
    end_ms: int | None = None,
    refresh: bool = False,
) -> pl.DataFrame:
    """Fetch typed funding settlements using the shared disk cache."""

    return _default_api().funding_history(
        coin, start_ms, end_ms=end_ms, refresh=refresh
    )


def candle_snapshot(
    coin: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    *,
    refresh: bool = False,
) -> pl.DataFrame:
    """Fetch typed OHLCV candles using the shared disk cache."""

    return _default_api().candle_snapshot(
        coin, interval, start_ms, end_ms, refresh=refresh
    )
