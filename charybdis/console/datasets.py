"""Read-only access to the research parquet tables.

A dataset name resolves, in order, to: a report table (data/reports/<name>.parquet),
a loose parquet next to the raw archive (data/<name>.parquet), or a directory of
part files (data/reports/<name>/*.parquet) scanned as one table.
"""
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


def data_root() -> Path:
    """Parent of the reports dir — loose parquets and the raw T-* archive."""
    return data_dir().parent


def dataset_path(name: str) -> Path:
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"invalid dataset name: {name}")
    candidates = (
        data_dir() / f"{name}.parquet",
        data_root() / f"{name}.parquet",
        data_dir() / name,
    )
    for p in candidates[:2]:
        if p.is_file():
            return p
    if _is_parts_dir(candidates[2]):
        return candidates[2]
    return candidates[0]


def _is_parts_dir(p: Path) -> bool:
    return p.is_dir() and next(p.glob("*.parquet"), None) is not None


def dataset_exists(name: str) -> bool:
    p = dataset_path(name)
    return p.is_file() or _is_parts_dir(p)


def _entry(name: str, paths: list[Path], kind: str) -> dict:
    stats = [p.stat() for p in paths]
    return {
        "name": name,
        "kind": kind,
        "files": len(paths),
        "columns": len(pl.read_parquet_schema(paths[0])),
        "size_bytes": sum(s.st_size for s in stats),
        "mtime": max(s.st_mtime for s in stats),
    }


def list_datasets() -> list[dict]:
    out: dict[str, dict] = {}
    root = data_dir()
    if root.is_dir():
        for p in sorted(root.glob("*.parquet")):
            out[p.stem] = _entry(p.stem, [p], "table")
        for d in sorted(root.iterdir()):
            if d.name not in out and _is_parts_dir(d):
                out[d.name] = _entry(d.name, sorted(d.glob("*.parquet")), "parts")
    loose = data_root()
    if loose.is_dir():
        for p in sorted(loose.glob("*.parquet")):
            if p.stem not in out:
                out[p.stem] = _entry(p.stem, [p], "table")
    return [out[k] for k in sorted(out)]


def scan_dataset(name: str) -> pl.LazyFrame:
    p = dataset_path(name)
    if p.is_file():
        return pl.scan_parquet(p)
    if _is_parts_dir(p):
        return pl.scan_parquet(sorted(p.glob("*.parquet")))
    raise FileNotFoundError(name)


def cached_payload(key: str, name: str, builder: Callable[[], Any]) -> Any:
    """Cache a computed payload, invalidated when the backing parquet's mtime changes."""
    mtime = dataset_path(name).stat().st_mtime
    hit = _PAYLOAD_CACHE.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    payload = builder()
    _PAYLOAD_CACHE[key] = (mtime, payload)
    return payload
