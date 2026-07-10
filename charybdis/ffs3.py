"""CoinAPI flat-files S3 listing, costing, and guarded downloads."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import json
import os
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, TextIO

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


GB = 1_000_000_000
ENDPOINT_URL = "https://s3.flatfiles.coinapi.io/"
BUCKET = "coinapi"
REGION = "us-east-1"
PAUSE_USD = 178.0
MAX_REQUESTS_PER_MINUTE = 640

# Each limit is the cumulative byte boundary for that tier. CoinAPI's published
# "GB" prices are treated as decimal gigabytes.
TRADES_PRICE_TIERS = (
    (GB // 2, Decimal("24")),
    (5 * GB, Decimal("12")),
    (None, Decimal("6")),
)
PRICE_TIERS: dict[str, tuple[tuple[int | None, Decimal], ...]] = {
    "Order Book": (
        (1 * GB, Decimal("8")),
        (10 * GB, Decimal("4")),
        (None, Decimal("2")),
    ),
    "Trades": TRADES_PRICE_TIERS,
    "Quotes": (
        (GB // 2, Decimal("8")),
        (5 * GB, Decimal("4")),
        (None, Decimal("2")),
    ),
    # CoinAPI does not publish separate rates for these Hyperliquid feeds.
    # Treat each as its own meter SKU while conservatively applying Trades rates.
    "HL Oracle Prices": TRADES_PRICE_TIERS,
    "HL System Events": TRADES_PRICE_TIERS,
    "HL TWAP Statuses": TRADES_PRICE_TIERS,
}
ASSUMED_PRICE_SKUS = frozenset(
    {"HL Oracle Prices", "HL System Events", "HL TWAP Statuses"}
)


@dataclass(frozen=True, slots=True)
class ObjectInfo:
    """A listed flat-file object and its compressed byte size."""

    key: str
    size: int


@dataclass(frozen=True, slots=True)
class ManifestFile:
    key: str
    size: int
    sku: str
    estimated_cost_usd: float


@dataclass(frozen=True, slots=True)
class Manifest:
    files: tuple[ManifestFile, ...]
    billing_day: str
    current_spend_usd: float
    estimated_cost_usd: float

    @property
    def projected_spend_usd(self) -> float:
        return self.current_spend_usd + self.estimated_cost_usd

    @property
    def paused(self) -> bool:
        return self.projected_spend_usd >= PAUSE_USD


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    downloaded: int
    skipped: int
    paused: bool


class DownloadClient(Protocol):
    def download_file(self, key: str, destination: Path) -> None: ...


class FlatFilesS3Client:
    """Minimal path-style S3 client for CoinAPI flat files."""

    def __init__(self, api_key: str | None = None, *, s3_client: Any | None = None) -> None:
        self._rate_lock = threading.Lock()
        self._next_request_at = 0.0
        if s3_client is not None:
            self._s3 = s3_client
            return
        access_key = api_key or os.environ.get("COINAPI_API_KEY")
        if not access_key:
            raise RuntimeError("COINAPI_API_KEY is not set")
        self._s3 = boto3.client(
            "s3",
            endpoint_url=ENDPOINT_URL,
            region_name=REGION,
            aws_access_key_id=access_key,
            aws_secret_access_key="coinapi",
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def list_with_sizes(self, prefix: str) -> list[ObjectInfo]:
        """List every object below a prefix using ListObjects V1 pagination."""

        objects: list[ObjectInfo] = []
        marker: str | None = None
        while True:
            request: dict[str, Any] = {"Bucket": BUCKET, "Prefix": prefix}
            if marker is not None:
                request["Marker"] = marker
            response = self._request_with_backoff("list_objects", **request)
            page = [
                ObjectInfo(key=item["Key"], size=int(item["Size"]))
                for item in response.get("Contents", [])
            ]
            objects.extend(page)
            if not response.get("IsTruncated"):
                break
            marker = response.get("NextMarker")
            if marker is None:
                if not page:
                    raise RuntimeError("truncated ListObjects response has no continuation marker")
                marker = page[-1].key
        return objects

    def download_file(self, key: str, destination: Path) -> None:
        """Stream one paid object to an atomic on-disk destination."""

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".part")
        for attempt in range(7):
            temporary.unlink(missing_ok=True)
            try:
                response = self._request_with_backoff(
                    "get_object", Bucket=BUCKET, Key=key
                )
                with temporary.open("wb") as output:
                    for chunk in response["Body"].iter_chunks(chunk_size=1024 * 1024):
                        if chunk:
                            output.write(chunk)
                temporary.replace(destination)
                return
            except (BotoCoreError, OSError, ClientError):
                temporary.unlink(missing_ok=True)
                if attempt == 6:
                    raise
                time.sleep(min(16.0, 0.5 * (2**attempt)))

    def _request_with_backoff(self, method_name: str, **kwargs: Any) -> Any:
        """Rate-limit requests and explicitly back off CoinAPI 403/429 replies."""

        method = getattr(self._s3, method_name)
        for attempt in range(7):
            self._wait_for_request_slot()
            try:
                return method(**kwargs)
            except ClientError as error:
                metadata = error.response.get("ResponseMetadata", {})
                status = int(metadata.get("HTTPStatusCode", 0) or 0)
                code = str(error.response.get("Error", {}).get("Code", ""))
                if status not in {403, 429} and code not in {
                    "403",
                    "429",
                    "SlowDown",
                    "Throttling",
                    "TooManyRequestsException",
                }:
                    raise
                if attempt == 6:
                    raise
                time.sleep(min(16.0, 0.5 * (2**attempt)))
        raise AssertionError("unreachable retry loop")

    def _wait_for_request_slot(self) -> None:
        interval = 60.0 / MAX_REQUESTS_PER_MINUTE
        with self._rate_lock:
            now = time.monotonic()
            delay = max(0.0, self._next_request_at - now)
            self._next_request_at = max(now, self._next_request_at) + interval
        if delay:
            time.sleep(delay)


def tier_cost_usd(sku: str, byte_count: int) -> Decimal:
    """Return cumulative cost for one SKU on one billing day."""

    if byte_count < 0:
        raise ValueError("byte_count cannot be negative")
    try:
        tiers = PRICE_TIERS[sku]
    except KeyError as exc:
        raise ValueError(f"unpriced dataset SKU: {sku}") from exc

    remaining = byte_count
    previous_limit = 0
    cost = Decimal("0")
    for limit, rate_per_gb in tiers:
        capacity = remaining if limit is None else min(remaining, limit - previous_limit)
        cost += Decimal(capacity) / Decimal(GB) * rate_per_gb
        remaining -= capacity
        if remaining == 0:
            break
        if limit is not None:
            previous_limit = limit
    return cost


class SpendMeter:
    """Persistent byte and estimated-cost accounting by billing day and SKU."""

    def __init__(self, path: str | Path = "data/spend.json") -> None:
        self.path = Path(path)
        self.lock_path = Path(f"{self.path}.lock")
        with self._locked_state():
            pass

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "days": {}, "running_cost_usd": 0.0}
        state = json.loads(self.path.read_text(encoding="utf-8"))
        if state.get("version") != 1 or not isinstance(state.get("days"), dict):
            raise ValueError(f"unsupported spend-meter state in {self.path}")
        return state

    @contextmanager
    def _locked_state(self, *, exclusive: bool = False) -> Iterator[dict[str, Any]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            fcntl.flock(lock_file.fileno(), operation)
            try:
                yield self._load_unlocked()
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _bytes_for_state(state: dict[str, Any], sku: str, billing_day: str) -> int:
        entry = state["days"].get(billing_day, {}).get(sku, {})
        return int(entry.get("bytes", 0))

    @property
    def running_cost_usd(self) -> float:
        with self._locked_state() as state:
            return float(state["running_cost_usd"])

    def bytes_for(self, sku: str, billing_day: str) -> int:
        with self._locked_state() as state:
            return self._bytes_for_state(state, sku, billing_day)

    def snapshot(self, billing_day: str) -> tuple[float, dict[str, int]]:
        """Read running spend and per-SKU bytes from one locked state."""

        with self._locked_state() as state:
            day = state["days"].get(billing_day, {})
            bytes_by_sku = {
                sku: int(entry.get("bytes", 0)) for sku, entry in day.items()
            }
            return float(state["running_cost_usd"]), bytes_by_sku

    def estimate(self, sku: str, billing_day: str, byte_count: int) -> float:
        """Estimate marginal cost without mutating persistent state."""

        if byte_count < 0:
            raise ValueError("byte_count cannot be negative")
        with self._locked_state() as state:
            existing = self._bytes_for_state(state, sku, billing_day)
            incremental = tier_cost_usd(sku, existing + byte_count) - tier_cost_usd(
                sku, existing
            )
            return float(incremental)

    def record(self, sku: str, billing_day: str, byte_count: int) -> float:
        """Record a completed download and return its marginal estimated cost."""

        if byte_count < 0:
            raise ValueError("byte_count cannot be negative")
        with self._locked_state(exclusive=True) as state:
            existing = self._bytes_for_state(state, sku, billing_day)
            total_bytes = existing + byte_count
            incremental = tier_cost_usd(sku, total_bytes) - tier_cost_usd(sku, existing)
            day = state["days"].setdefault(billing_day, {})
            day[sku] = {
                "bytes": total_bytes,
                "cost_usd": float(tier_cost_usd(sku, total_bytes)),
            }
            state["running_cost_usd"] = float(state["running_cost_usd"]) + float(
                incremental
            )
            self._persist_unlocked(state)
            return float(incremental)

    def _persist_unlocked(self, state: dict[str, Any]) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


def sku_from_key(key: str) -> str:
    """Map the flat-file dataset component to its priced SKU."""

    dataset = key.split("/", 1)[0]
    mapping = {
        "T-LIMITBOOK_FULL": "Order Book",
        "T-TRADES": "Trades",
        "T-QUOTES": "Quotes",
        "T-HLORACLEPRICES": "HL Oracle Prices",
        "T-HLSYSTEMEVENTS": "HL System Events",
        "T-HLTWAPSTATUSES": "HL TWAP Statuses",
    }
    try:
        return mapping[dataset]
    except KeyError as exc:
        raise ValueError(f"no pricing tier configured for dataset {dataset!r}") from exc


def build_manifest(
    objects: list[ObjectInfo],
    meter: SpendMeter,
    *,
    billing_day: str | None = None,
    data_root: str | Path = "data",
) -> Manifest:
    """Cost listed objects in order, including their per-file marginal prices."""

    day = billing_day or datetime.now(UTC).date().isoformat()
    current_spend, existing_bytes = meter.snapshot(day)
    root = Path(data_root)
    planned_bytes: dict[str, int] = {}
    files: list[ManifestFile] = []
    total_cost = Decimal("0")
    for item in objects:
        if item.size < 0:
            raise ValueError(f"negative object size for {item.key}")
        if not item.key.endswith(".gz"):
            raise ValueError(f"refusing non-gzipped object: {item.key}")
        sku = sku_from_key(item.key)
        destination = _destination_for(root, item.key)
        already_present = (
            destination.exists() and destination.stat().st_size == item.size
        )
        existing = existing_bytes.get(sku, 0)
        before = existing + planned_bytes.get(sku, 0)
        incremental = Decimal("0")
        if not already_present:
            incremental = tier_cost_usd(sku, before + item.size) - tier_cost_usd(
                sku, before
            )
            planned_bytes[sku] = planned_bytes.get(sku, 0) + item.size
        total_cost += incremental
        files.append(
            ManifestFile(
                key=item.key,
                size=item.size,
                sku=sku,
                estimated_cost_usd=float(incremental),
            )
        )
    return Manifest(
        files=tuple(files),
        billing_day=day,
        current_spend_usd=current_spend,
        estimated_cost_usd=float(total_cost),
    )


def _destination_for(data_root: Path, key: str) -> Path:
    relative = Path(key)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe object key: {key!r}")
    return data_root / relative


def execute_manifest(
    client: DownloadClient,
    manifest: Manifest,
    meter: SpendMeter,
    *,
    data_root: str | Path = "data",
    dry_run: bool = False,
    workers: int = 1,
    output: TextIO = sys.stdout,
) -> ExecutionResult:
    """Print a plan, enforce G3, and optionally download its gzipped files."""

    if abs(meter.running_cost_usd - manifest.current_spend_usd) > 1e-9:
        raise RuntimeError("spend meter changed after manifest was built; rebuild it")

    mode = "DRY-RUN" if dry_run else "DOWNLOAD"
    print(
        f"{mode} files={len(manifest.files)} bytes={sum(f.size for f in manifest.files)} "
        f"cost=${manifest.estimated_cost_usd:.2f} "
        f"projected=${manifest.projected_spend_usd:.2f}",
        file=output,
    )
    for item in manifest.files:
        print(
            f"{item.sku}\t{item.size}\t${item.estimated_cost_usd:.6f}\t{item.key}",
            file=output,
        )

    if manifest.paused:
        print(
            f"PAUSE projected spend reaches G3 ceiling ${PAUSE_USD:.2f}; no downloads",
            file=output,
        )
        return ExecutionResult(downloaded=0, skipped=0, paused=True)
    if dry_run:
        print("DRY-RUN complete; no downloads", file=output)
        return ExecutionResult(downloaded=0, skipped=0, paused=False)

    if not isinstance(workers, int) or isinstance(workers, bool) or not 1 <= workers <= 8:
        raise ValueError("workers must be an integer from 1 through 8")
    root = Path(data_root)
    downloaded = 0
    skipped = 0
    pending: list[tuple[ManifestFile, Path]] = []
    for item in manifest.files:
        destination = _destination_for(root, item.key)
        if destination.exists() and destination.stat().st_size == item.size:
            print(f"SKIP existing {item.key}", file=output)
            skipped += 1
            continue
        pending.append((item, destination))

    def download_one(item: ManifestFile, destination: Path) -> int:
        client.download_file(item.key, destination)
        actual_size = destination.stat().st_size
        if actual_size != item.size:
            destination.unlink(missing_ok=True)
            raise IOError(
                f"size mismatch for {item.key}: expected {item.size}, got {actual_size}"
            )
        meter.record(item.sku, manifest.billing_day, actual_size)
        return actual_size

    if workers == 1:
        for item, destination in pending:
            download_one(item, destination)
            downloaded += 1
            print(f"DOWNLOADED {item.key}", file=output)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(download_one, item, destination): item
                for item, destination in pending
            }
            for future in as_completed(futures):
                item = futures[future]
                future.result()
                downloaded += 1
                print(f"DOWNLOADED {item.key}", file=output)
    return ExecutionResult(downloaded=downloaded, skipped=skipped, paused=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix", help="CoinAPI S3 prefix to list and plan")
    parser.add_argument("--dry-run", action="store_true", help="list and cost only")
    parser.add_argument("--billing-day", help="UTC billing day (YYYY-MM-DD)")
    parser.add_argument("--data-root", default="data")
    parser.add_argument("--spend-file", default="data/spend.json")
    args = parser.parse_args(argv)

    client = FlatFilesS3Client()
    objects = client.list_with_sizes(args.prefix)
    meter = SpendMeter(args.spend_file)
    manifest = build_manifest(
        objects,
        meter,
        billing_day=args.billing_day,
        data_root=args.data_root,
    )
    result = execute_manifest(
        client,
        manifest,
        meter,
        data_root=args.data_root,
        dry_run=args.dry_run,
    )
    return 2 if result.paused else 0


if __name__ == "__main__":
    raise SystemExit(main())
