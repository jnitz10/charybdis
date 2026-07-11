"""Read-only access to the report parquet tables in data/reports/."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import polars as pl

# key -> (mtime, payload); cleared by tests via _PAYLOAD_CACHE.clear()
_PAYLOAD_CACHE: dict[str, tuple[float, Any]] = {}


def data_dir() -> Path:
    env = os.environ.get("CHARYBDIS_DATA_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "data" / "reports"


def dataset_path(name: str) -> Path:
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"invalid dataset name: {name}")
    return data_dir() / f"{name}.parquet"


def dataset_exists(name: str) -> bool:
    return dataset_path(name).is_file()


def list_datasets() -> list[dict]:
    root = data_dir()
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.glob("*.parquet")):
        stat = p.stat()
        out.append(
            {
                "name": p.stem,
                "columns": len(pl.read_parquet_schema(p)),
                "size_bytes": stat.st_size,
                "mtime": stat.st_mtime,
            }
        )
    return out


def scan_dataset(name: str) -> pl.LazyFrame:
    p = dataset_path(name)
    if not p.is_file():
        raise FileNotFoundError(name)
    return pl.scan_parquet(p)


def cached_payload(key: str, name: str, builder: Callable[[], Any]) -> Any:
    """Cache a computed payload, invalidated when the backing parquet's mtime changes."""
    mtime = dataset_path(name).stat().st_mtime
    hit = _PAYLOAD_CACHE.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    payload = builder()
    _PAYLOAD_CACHE[key] = (mtime, payload)
    return payload
