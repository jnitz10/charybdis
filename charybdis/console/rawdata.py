"""Read-only browsing of the raw CoinAPI flat-file archive (data/T-*).

The archive is day/hour-partitioned gzip CSVs (~21 GB); everything here is
lazy — files are only decompressed for single-file previews and per-market
candle builds, never for listings. Listings come from a filename index cached
per feed and invalidated by the feed directory's mtime (new partitions touch
it; the archive is append-only, so files inside existing partitions are
assumed immutable).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from charybdis import loaders
from charybdis.console import datasets

_S_RE = re.compile(r"\+S-(?P<coin>.+?)\.csv\.gz$")
_ERAS = {"HYPERLIQUID": "l2", "HYPERLIQUIDL4": "l4"}
_TIME_COLUMNS = ("time_exchange", "time_coinapi")

# feed -> (feed dir mtime, files)
_INDEX_CACHE: dict[str, tuple[float, list["RawFile"]]] = {}
# (market, every) -> (T-TRADES mtime, (ohlcv frame, warnings))
_CANDLE_CACHE: dict[tuple[str, str], tuple[float, tuple[pl.DataFrame, list[str]]]] = {}


@dataclass(frozen=True)
class RawFile:
    feed: str
    partition: str  # D-YYYYMMDD (L2, daily) or D-YYYYMMDDHH (L4, hourly)
    era: str  # "l2" | "l4" | lowercased exchange id
    market: str  # e.g. "xyz:SKHX"; "all" for whole-exchange files (HLSYSTEMEVENTS)
    size_bytes: int
    rel: str  # path relative to raw_root()

    @property
    def day(self) -> str:
        d = self.partition[2:10]
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def raw_root() -> Path:
    env = os.environ.get("CHARYBDIS_RAW_DIR")
    if env:
        return Path(env)
    return datasets.data_dir().parent


def _market_from_name(name: str) -> str:
    m = _S_RE.search(name)
    if m is None:
        return "all"
    coin = m.group("coin").replace("__003A", ":")
    if ":" in coin:
        dex, asset = coin.split(":", 1)
        return f"{dex.lower()}:{asset}"
    return coin


def _era_from_exchange(exchange: str) -> str:
    return _ERAS.get(exchange, exchange.lower())


def _validate_name(value: str, what: str) -> None:
    if not value or "/" in value or "\\" in value or ".." in value:
        raise ValueError(f"invalid {what}: {value!r}")


def index(feed: str) -> list[RawFile]:
    _validate_name(feed, "feed")
    root = raw_root() / f"T-{feed}"
    if not root.is_dir():
        raise FileNotFoundError(f"feed not present: {feed}")
    mtime = root.stat().st_mtime
    hit = _INDEX_CACHE.get(feed)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    out: list[RawFile] = []
    for part_dir in sorted(root.iterdir()):
        if not part_dir.is_dir() or not part_dir.name.startswith("D-"):
            continue
        for entry in part_dir.iterdir():
            if entry.is_file() and entry.name.endswith(".csv.gz"):
                # whole-exchange file directly in the partition (HLSYSTEMEVENTS)
                exchange = entry.name.removesuffix(".csv.gz").removeprefix("E-")
                out.append(_raw_file(feed, part_dir, entry, exchange))
            elif entry.is_dir() and entry.name.startswith("E-"):
                exchange = entry.name[2:]
                for f in entry.iterdir():
                    if f.is_file() and f.name.endswith(".csv.gz"):
                        out.append(_raw_file(feed, part_dir, f, exchange))
    _INDEX_CACHE[feed] = (mtime, out)
    return out


def _raw_file(feed: str, part_dir: Path, f: Path, exchange: str) -> RawFile:
    return RawFile(
        feed=feed,
        partition=part_dir.name,
        era=_era_from_exchange(exchange),
        market=_market_from_name(f.name),
        size_bytes=f.stat().st_size,
        rel=str(f.relative_to(raw_root())),
    )


def list_feeds() -> list[dict]:
    root = raw_root()
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.glob("T-*")):
        if not d.is_dir():
            continue
        files = index(d.name[2:])
        if not files:
            continue
        partitions = sorted({f.partition for f in files})
        out.append(
            {
                "feed": d.name[2:],
                "partitions": len(partitions),
                "files": len(files),
                "size_bytes": sum(f.size_bytes for f in files),
                "first_day": min(f.day for f in files),
                "last_day": max(f.day for f in files),
                "eras": sorted({f.era for f in files}),
                "markets": len({f.market for f in files}),
            }
        )
    return out


def markets(feed: str) -> list[dict]:
    grouped: dict[str, list[RawFile]] = {}
    for f in index(feed):
        grouped.setdefault(f.market, []).append(f)
    out = []
    for market, files in sorted(grouped.items()):
        out.append(
            {
                "market": market,
                "files": len(files),
                "size_bytes": sum(f.size_bytes for f in files),
                "first_day": min(f.day for f in files),
                "last_day": max(f.day for f in files),
                "eras": sorted({f.era for f in files}),
            }
        )
    return out


def files(feed: str, market: str | None = None, partition: str | None = None) -> list[dict]:
    out = [
        {
            "partition": f.partition,
            "day": f.day,
            "era": f.era,
            "market": f.market,
            "size_bytes": f.size_bytes,
        }
        for f in index(feed)
        if (market is None or f.market == market)
        and (partition is None or f.partition == partition)
    ]
    return sorted(out, key=lambda d: (d["partition"], d["market"]))


def _scan_file(path: Path) -> pl.LazyFrame:
    try:
        return loaders.scan_flat_file(path)
    except ValueError:
        # non-standard key (oracle prices, system events): plain CoinAPI CSV
        # conventions, full timestamps — no era/date-stamping needed
        lf = pl.scan_csv(
            path,
            separator=";",
            null_values="",
            infer_schema_length=1000,
            low_memory=True,
            rechunk=False,
        )
        names = lf.collect_schema().names()
        return lf.with_columns(
            [
                pl.col(c).cast(pl.String).str.to_datetime(time_unit="ns", strict=True)
                for c in _TIME_COLUMNS
                if c in names
            ]
        )


def preview(feed: str, partition: str, market: str, limit: int = 100) -> dict:
    limit = min(max(1, limit), 500)
    matches = [f for f in index(feed) if f.partition == partition and f.market == market]
    if not matches:
        raise FileNotFoundError(
            f"no raw file for feed={feed} partition={partition} market={market}"
        )
    f = matches[0]
    lf = _scan_file(raw_root() / f.rel)
    schema = lf.collect_schema()
    total = lf.select(pl.len()).collect().item()
    df = lf.head(limit).collect()
    from charybdis.console.tables import json_value

    return {
        "feed": feed,
        "partition": partition,
        "day": f.day,
        "era": f.era,
        "market": market,
        "size_bytes": f.size_bytes,
        "total": total,
        "columns": [{"name": c, "dtype": str(t)} for c, t in schema.items()],
        "rows": [[json_value(v) for v in row] for row in df.rows()],
    }


def trade_markets() -> list[str]:
    try:
        return sorted({f.market for f in index("TRADES") if f.market != "all"})
    except FileNotFoundError:
        return []


def _tick_scan(paths: list[Path]) -> pl.LazyFrame:
    return pl.scan_csv(
        paths,
        separator=";",
        null_values="",
        schema_overrides={"price": pl.Float64, "base_amount": pl.Float64},
        infer_schema_length=1000,
        low_memory=True,
        rechunk=False,
    ).select(
        pl.col("time_exchange").cast(pl.String).str.to_datetime(time_unit="ns"),
        pl.col("price"),
        pl.col("base_amount"),
    )


def _collect_ticks(paths: list[Path]) -> tuple[pl.DataFrame, list[str]]:
    """Collect tick columns, salvaging file-by-file around corrupt gzips."""
    try:
        return _tick_scan(paths).collect(), []
    except OSError:
        frames, skipped = [], []
        for p in paths:
            try:
                frames.append(_tick_scan([p]).collect())
            except OSError:
                skipped.append(p.name)
        if not frames:
            raise
        return pl.concat(frames), skipped


def trade_candles(market: str, every: str) -> tuple[pl.DataFrame, list[str]]:
    """OHLCV at `every` resolution from raw T-TRADES ticks for one market.

    Where the L2 and L4 coverage eras overlap on a calendar day the L4 files
    win — both eras carry the same prints for the overlap window, so keeping
    both would double volume. Returns (frame, warnings); corrupt files are
    skipped and reported, never silently absorbed.
    """
    all_files = [f for f in index("TRADES") if f.market == market]
    if not all_files:
        raise LookupError(f"no raw trades for market {market!r}")
    mtime = (raw_root() / "T-TRADES").stat().st_mtime
    hit = _CANDLE_CACHE.get((market, every))
    if hit is not None and hit[0] == mtime:
        return hit[1]
    l4_days = {f.day for f in all_files if f.era == "l4"}
    frames: list[pl.DataFrame] = []
    warnings: list[str] = []
    for era in ("l2", "l4"):
        paths = [
            raw_root() / f.rel
            for f in all_files
            if f.era == era and (era == "l4" or f.day not in l4_days)
        ]
        if not paths:
            continue
        # eras have different column sets (L4 adds wallet attribution), so
        # each era is one scan and the projected columns are concatenated
        ticks, skipped = _collect_ticks(paths)
        if skipped:
            warnings.append(f"skipped {len(skipped)} corrupt file(s): {', '.join(skipped)}")
        if ticks.height:
            frames.append(ticks)
    if not frames:
        raise LookupError(f"no readable trades for market {market!r}")
    ohlcv = (
        pl.concat(frames)
        .lazy()
        .sort("time_exchange")
        .group_by_dynamic("time_exchange", every=every)
        .agg(
            open=pl.col("price").first(),
            high=pl.col("price").max(),
            low=pl.col("price").min(),
            close=pl.col("price").last(),
            volume=pl.col("base_amount").sum(),
        )
        .select(
            pl.col("time_exchange").dt.epoch(time_unit="s").alias("time_s"),
            "open",
            "high",
            "low",
            "close",
            "volume",
        )
        .collect()
    )
    _CANDLE_CACHE[(market, every)] = (mtime, (ohlcv, warnings))
    return ohlcv, warnings
