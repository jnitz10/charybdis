from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import random
import time

import httpx
import polars as pl

from charybdis.book import reconstruct_l1
from charybdis.calendars import label_nyse
from charybdis.loaders import parse_flat_file_key, scan_book_events, scan_trades
from charybdis.markout import (
    HORIZONS_SECONDS,
    primary_summary,
    secondary_summary,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "reports"
PARTS = OUT / "study1_l2_parts"
STATS = OUT / "study1_l2_stats"
FUNDING_PATH = OUT / "study1_funding.parquet"
FUNDING_META = OUT / "study1_funding_meta.json"
FILLS_PATH = OUT / "study1_fills_l2.parquet"
OVERLAP_PATH = OUT / "study1_overlap_l2_l4.json"
RUN_META = OUT / "study1_run_meta.json"
REPORT_PATH = ROOT / "docs/reports/study1_offhours_markout_2026-07-09.md"

MARKETS = [
    "xyz:SP500",
    "km:US500",
    "flx:USA500",
    "cash:USA500",
    "km:USTECH",
    "xyz:XYZ100",
    "flx:USA100",
    "km:SMALL2000",
]
SEGMENTS = ["RTH", "off-hours-weekday", "weekend"]
START_MS = int(datetime(2026, 3, 10, tzinfo=UTC).timestamp() * 1000)
WINDOW_START = datetime(2026, 3, 11)
WINDOW_END = datetime(2026, 6, 9)
OVERLAP_START = datetime(2026, 5, 8)
OVERLAP_END = datetime(2026, 6, 9)
N_RESAMPLES = 2_000
MIN_CLUSTERS = 5


def inventory(dataset: str, era: str) -> dict[tuple[str, str], list[Path]]:
    exchange = "HYPERLIQUID" if era == "l2" else "HYPERLIQUIDL4"
    found: dict[tuple[str, str], list[Path]] = defaultdict(list)
    base = DATA / f"T-{dataset}"
    for path in base.glob(f"D-*/E-{exchange}/*.csv.gz"):
        key = parse_flat_file_key(path)
        market = next((item for item in MARKETS if item.lower() == key.coin.lower()), None)
        if market is not None:
            found[(market, key.partition[:8])].append(path)
    for paths in found.values():
        paths.sort()
    return dict(found)


def fetch_funding() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    meta: dict[str, object] = {"markets": {}, "request_interval_s": 1.0}
    last_request = 0.0
    with httpx.Client(timeout=30.0) as client:
        for market in MARKETS:
            cursor = START_MS
            market_rows: list[tuple[int, float]] = []
            calls = 0
            while cursor < int(WINDOW_END.replace(tzinfo=UTC).timestamp() * 1000):
                wait = 1.0 - (time.monotonic() - last_request)
                if wait > 0:
                    time.sleep(wait)
                response = client.post(
                    "https://api.hyperliquid.xyz/info",
                    json={"type": "fundingHistory", "coin": market, "startTime": cursor},
                )
                last_request = time.monotonic()
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, list):
                    raise RuntimeError(f"unexpected funding payload for {market}: {payload!r}")
                calls += 1
                parsed = sorted(
                    (int(item["time"]), float(item["fundingRate"])) for item in payload
                )
                if not parsed:
                    break
                end_ms = int(WINDOW_END.replace(tzinfo=UTC).timestamp() * 1000)
                market_rows.extend((ts, rate) for ts, rate in parsed if ts < end_ms)
                next_cursor = parsed[-1][0] + 1
                if next_cursor <= cursor:
                    raise RuntimeError(f"non-advancing funding cursor for {market}")
                cursor = next_cursor
                if len(parsed) < 500 or parsed[-1][0] >= end_ms:
                    break

            deduped = sorted(dict(market_rows).items())
            zero_series = not deduped
            zero_prefix = bool(deduped and deduped[0][0] > START_MS)
            if zero_series:
                deduped = [(START_MS, 0.0)]
            elif zero_prefix:
                deduped.insert(0, (START_MS, 0.0))
            for ts, rate in deduped:
                rows.append(
                    {
                        "time_exchange": datetime.fromtimestamp(ts / 1000, tz=UTC).replace(tzinfo=None),
                        "market": market,
                        "hourly_rate": rate,
                    }
                )
            meta["markets"][market] = {
                "calls": calls,
                "api_rows_in_window": len(market_rows),
                "zero_series": zero_series,
                "zero_prefix": zero_prefix,
            }
            print(f"funding {market}: calls={calls} rows={len(market_rows)} zero={zero_series}", flush=True)
    pl.DataFrame(rows).sort(["market", "time_exchange"]).write_parquet(FUNDING_PATH)
    FUNDING_META.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")


def segment_frame(times: pl.Series) -> pl.DataFrame:
    minute_values = (
        pl.DataFrame({"time_exchange": times})
        .select(pl.col("time_exchange").dt.truncate("1m").alias("minute"))
        .unique()
        .sort("minute")["minute"]
        .to_list()
    )
    labels = []
    for minute in minute_values:
        label = label_nyse(minute.replace(tzinfo=UTC))
        labels.append("off-hours-weekday" if label == "holiday" else label)
    return pl.DataFrame(
        {"minute": minute_values, "segment": labels},
        schema={"minute": pl.Datetime("ns"), "segment": pl.String},
    )


def sanitize_book_events(events: pl.DataFrame) -> tuple[pl.DataFrame, dict[str, int]]:
    keep = [True] * events.height
    sizes = events["entry_sx"].to_list()
    bids: dict[float, float] = {}
    asks: dict[float, float] = {}
    in_snapshot = False
    orphan_subs = 0
    oversize_subs = 0
    selected = events.select("update_type", "is_buy", "entry_px", "entry_sx")
    for index, (raw_type, is_buy, raw_price, raw_size) in enumerate(selected.iter_rows()):
        update_type = str(raw_type).upper()
        price = float(raw_price)
        size = float(raw_size)
        side = bids if bool(is_buy) else asks
        if update_type == "SNAPSHOT":
            if not in_snapshot:
                bids.clear()
                asks.clear()
                in_snapshot = True
            if size <= 0:
                side.pop(price, None)
            else:
                side[price] = size
            continue
        in_snapshot = False
        if update_type == "ADD":
            side[price] = side.get(price, 0.0) + size
        elif update_type == "SUB":
            existing = side.get(price)
            if existing is None:
                keep[index] = False
                orphan_subs += 1
                continue
            tolerance = max(1e-12, abs(existing) * 1e-12)
            if size > existing + tolerance:
                sizes[index] = existing
                size = existing
                oversize_subs += 1
            remaining = existing - size
            if remaining <= tolerance:
                side.pop(price, None)
            else:
                side[price] = remaining
        elif update_type in {"SET", "CHANGE", "UPDATE"}:
            if size <= 0:
                side.pop(price, None)
            else:
                side[price] = size
        elif update_type in {"DELETE", "REMOVE"}:
            side.pop(price, None)
    sanitized = events.with_columns(
        pl.Series("_keep", keep),
        pl.Series("entry_sx", sizes, dtype=pl.Float64),
    ).filter(pl.col("_keep")).drop("_keep")
    return sanitized, {"orphan_subs_dropped": orphan_subs, "oversize_subs_clamped": oversize_subs}


def census_stats(l1: pl.DataFrame, market: str) -> list[dict[str, object]]:
    if l1.is_empty():
        return []
    labels = segment_frame(l1["time_exchange"])
    valid = pl.all_horizontal(
        pl.col("best_bid_px").is_not_null(),
        pl.col("best_bid_sx").is_not_null(),
        pl.col("best_ask_px").is_not_null(),
        pl.col("best_ask_sx").is_not_null(),
        pl.col("best_bid_px") > 0,
        pl.col("best_bid_sx") > 0,
        pl.col("best_ask_px") > 0,
        pl.col("best_ask_sx") > 0,
        pl.col("best_bid_px") <= pl.col("best_ask_px"),
    )
    mid = (pl.col("best_bid_px") + pl.col("best_ask_px")) / 2.0
    frame = (
        l1.with_columns(
            pl.col("time_exchange").dt.truncate("1m").alias("minute"),
            pl.col("time_exchange").dt.truncate("6h").alias("block"),
            valid.alias("valid"),
            pl.when(valid)
            .then((pl.col("best_ask_px") - pl.col("best_bid_px")) / mid * 10_000.0)
            .otherwise(None)
            .alias("spread_bps"),
            pl.when(valid)
            .then(pl.col("best_bid_sx") + pl.col("best_ask_sx"))
            .otherwise(None)
            .alias("depth_units"),
        )
        .join(labels, on="minute", how="left")
        .group_by(["segment", "block"])
        .agg(
            pl.col("valid").cast(pl.Float64).sum().alias("uptime_num"),
            pl.len().alias("uptime_den"),
            pl.col("spread_bps").sum().alias("spread_num"),
            pl.col("spread_bps").count().alias("spread_den"),
            pl.col("depth_units").sum().alias("depth_num"),
            pl.col("depth_units").count().alias("depth_den"),
        )
        .sort(["segment", "block"])
    )
    result = []
    for row in frame.iter_rows(named=True):
        row = dict(row)
        row["market"] = market
        row["cluster_key"] = f"{market}|{row.pop('block').isoformat()}"
        result.append(row)
    return result


def latency_stats(trades: pl.DataFrame, market: str) -> list[dict[str, object]]:
    if trades.is_empty() or "time_coinapi" not in trades.columns:
        return []
    frame = (
        trades.with_columns(
            ((pl.col("time_coinapi") - pl.col("time_exchange")).dt.total_microseconds() / 1000.0)
            .alias("latency_ms"),
            pl.col("time_exchange").dt.truncate("6h").alias("block"),
        )
        .filter(pl.col("latency_ms").is_finite())
        .group_by("block")
        .agg(
            pl.col("latency_ms").sum().alias("latency_num"),
            pl.len().alias("latency_den"),
            (pl.col("latency_ms") < 0).cast(pl.Float64).sum().alias("negative_num"),
            (pl.col("latency_ms") <= 500).cast(pl.Float64).sum().alias("le500_num"),
            (pl.col("latency_ms") <= 1000).cast(pl.Float64).sum().alias("le1000_num"),
            (pl.col("latency_ms") <= 5000).cast(pl.Float64).sum().alias("le5000_num"),
        )
        .sort("block")
    )
    result = []
    for row in frame.iter_rows(named=True):
        row = dict(row)
        row["market"] = market
        row["cluster_key"] = f"{market}|{row.pop('block').isoformat()}"
        result.append(row)
    return result


def run_l2() -> None:
    if not FUNDING_PATH.exists():
        raise RuntimeError("funding parquet is absent; run --phase funding first")
    PARTS.mkdir(parents=True, exist_ok=True)
    STATS.mkdir(parents=True, exist_ok=True)
    books = inventory("LIMITBOOK_FULL", "l2")
    trades = inventory("TRADES", "l2")
    funding = pl.read_parquet(FUNDING_PATH)
    pairs = sorted(set(books) & set(trades), key=lambda item: (item[1], MARKETS.index(item[0])))
    missing_books = sorted(set(trades) - set(books))
    missing_trades = sorted(set(books) - set(trades))
    started = time.monotonic()
    processed = 0
    total_fills = 0
    for market, day in pairs:
        safe = market.replace(":", "__")
        fill_path = PARTS / f"{day}_{safe}.parquet"
        stat_path = STATS / f"{day}_{safe}.json"
        if fill_path.exists() and stat_path.exists():
            processed += 1
            total_fills += pl.scan_parquet(fill_path).select(pl.len()).collect().item()
            continue
        if len(books[(market, day)]) != 1 or len(trades[(market, day)]) != 1:
            raise RuntimeError(f"expected one L2 file for {market} {day}")
        book_events = scan_book_events(
            books[(market, day)][0],
            era="l2",
            columns=["time_exchange", "update_type", "is_buy", "entry_px", "entry_sx"],
        ).collect(engine="streaming")
        book_was_unsorted = not book_events["time_exchange"].is_sorted()
        trimmed_events = 0
        rotated_snapshot_rows_dropped = 0
        if book_was_unsorted:
            first_physical_time = book_events["time_exchange"][0]
            if (
                str(book_events["update_type"][0]).upper() == "SNAPSHOT"
                and first_physical_time > book_events["time_exchange"].min()
            ):
                rotated_snapshot_rows_dropped = book_events.filter(
                    pl.col("time_exchange") == first_physical_time
                ).height
                book_events = book_events.filter(
                    pl.col("time_exchange") != first_physical_time
                )
            book_events = book_events.sort("time_exchange", maintain_order=True)
        if book_events.height and str(book_events["update_type"][0]).upper() != "SNAPSHOT":
            first_snapshot = book_events.filter(
                pl.col("update_type").str.to_uppercase() == "SNAPSHOT"
            )["time_exchange"].min()
            if first_snapshot is None:
                raise RuntimeError(f"no usable snapshot in L2 book for {market} {day}")
            trimmed_events = book_events.filter(pl.col("time_exchange") < first_snapshot).height
            book_events = book_events.filter(pl.col("time_exchange") >= first_snapshot)
        book_events, sanitation = sanitize_book_events(book_events)
        l1 = reconstruct_l1(book_events)
        crossed = (
            pl.col("best_bid_px").is_not_null()
            & pl.col("best_ask_px").is_not_null()
            & (pl.col("best_bid_px") > pl.col("best_ask_px"))
        )
        crossed_l1_rows_invalidated = l1.filter(crossed).height
        if crossed_l1_rows_invalidated:
            l1 = l1.with_columns(
                [
                    pl.when(crossed).then(None).otherwise(pl.col(column)).alias(column)
                    for column in ["best_bid_px", "best_bid_sx", "best_ask_px", "best_ask_sx"]
                ]
            )
        del book_events
        trade_frame = scan_trades(
            trades[(market, day)][0],
            era="l2",
            columns=["time_exchange", "time_coinapi", "price", "base_amount"],
        ).collect(engine="streaming")
        if not trade_frame["time_exchange"].is_sorted():
            trade_frame = trade_frame.sort("time_exchange", maintain_order=True)
        if not l1["time_exchange"].is_sorted():
            l1 = l1.sort("time_exchange")
        from charybdis.markout import build_fill_markouts

        fills = build_fill_markouts(
            l1,
            trade_frame.select("time_exchange", "price", "base_amount"),
            market=market,
            funding=funding,
            maker_fee_bps=1.5,
            max_quote_age_s=60.0,
            horizons=HORIZONS_SECONDS,
        )
        fills.write_parquet(fill_path, compression="zstd")
        stats = {
            "market": market,
            "day": day,
            "l1_rows": l1.height,
            "trade_rows": trade_frame.height,
            "fill_rows": fills.height,
            "book_was_unsorted": book_was_unsorted,
            "pre_snapshot_events_trimmed": trimmed_events,
            "rotated_snapshot_rows_dropped": rotated_snapshot_rows_dropped,
            "crossed_l1_rows_invalidated": crossed_l1_rows_invalidated,
            **sanitation,
            "census": census_stats(l1, market),
            "latency": latency_stats(trade_frame, market),
        }
        stat_path.write_text(json.dumps(stats, default=str, sort_keys=True) + "\n")
        processed += 1
        total_fills += fills.height
        elapsed = time.monotonic() - started
        print(
            f"l2 {processed}/{len(pairs)} {market} {day}: l1={l1.height} trades={trade_frame.height} fills={fills.height} elapsed={elapsed:.1f}s",
            flush=True,
        )
        del l1, trade_frame, fills

    part_files = sorted(PARTS.glob("*.parquet"))
    total_fills = pl.scan_parquet(part_files).select(pl.len()).collect(engine="streaming").item()
    if total_fills == 0:
        raise RuntimeError("BLOCKER_SYSTEMIC_EMPTY_FILLS: all L2 market-days produced zero fills")
    if FILLS_PATH.exists():
        FILLS_PATH.unlink()
    pl.scan_parquet(part_files).sink_parquet(FILLS_PATH, compression="zstd")
    meta = {
        "market_days_processed": len(pairs),
        "total_fills": total_fills,
        "missing_book_market_days": [(m, d) for m, d in missing_books],
        "missing_trade_market_days": [(m, d) for m, d in missing_trades],
        "l2_wall_seconds": time.monotonic() - started,
        "memory_cap": "prlimit --as=6442450944 (systemd user manager unreachable)",
    }
    RUN_META.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")


def cluster_from_time(frame: pl.DataFrame, market: str) -> pl.DataFrame:
    return frame.with_columns(
        pl.col("time_exchange").dt.truncate("6h").dt.strftime("%Y-%m-%dT%H:00:00").alias("block")
    ).with_columns((pl.lit(market + "|") + pl.col("block")).alias("cluster_key"))


def collect_trade_paths(paths: list[Path], era: str, skipped: list[str]) -> pl.DataFrame:
    frames = []
    for path in paths:
        try:
            frames.append(
                scan_trades(
                    path,
                    era=era,
                    columns=["time_exchange", "price", "base_amount"],
                ).collect(engine="streaming")
            )
        except OSError as exc:
            skipped.append(f"{path.relative_to(ROOT)}: {exc}")
    if frames:
        return pl.concat(frames)
    return pl.DataFrame(
        schema={
            "time_exchange": pl.Datetime("ns"),
            "price": pl.Float64,
            "base_amount": pl.Float64,
        }
    )


def run_overlap() -> None:
    l2_files = inventory("TRADES", "l2")
    l4_files = inventory("TRADES", "l4")
    output: dict[str, object] = {
        "markets": {},
        "window": ["2026-05-08", "2026-06-08"],
        "skipped_files": [],
    }
    for market in MARKETS:
        clusters: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        days = sorted(
            d
            for m, d in set(l2_files) | set(l4_files)
            if m == market and OVERLAP_START.date() <= datetime.strptime(d, "%Y%m%d").date() < OVERLAP_END.date()
        )
        for day in days:
            print(f"overlap {market} {day}", flush=True)
            l2_paths = l2_files.get((market, day), [])
            l4_paths = l4_files.get((market, day), [])
            l2 = collect_trade_paths(l2_paths, "l2", output["skipped_files"])
            l4 = collect_trade_paths(l4_paths, "l4", output["skipped_files"])
            l2 = cluster_from_time(l2, market)
            l4 = cluster_from_time(l4, market)
            for key, count in l2.group_by("cluster_key").len().iter_rows():
                clusters[key]["l2"] += count
            for key, count in l4.group_by("cluster_key").len().iter_rows():
                clusters[key]["l4"] += count

            if not l2.is_empty() and not l4.is_empty():
                a = l2.group_by(["cluster_key", "time_exchange", "price", "base_amount"]).len().rename({"len": "n2"})
                b = l4.group_by(["cluster_key", "time_exchange", "price", "base_amount"]).len().rename({"len": "n4"})
                exact = a.join(b, on=["cluster_key", "time_exchange", "price", "base_amount"], how="inner").with_columns(pl.min_horizontal("n2", "n4").alias("matched"))
                for key, matched in exact.group_by("cluster_key").agg(pl.col("matched").sum()).iter_rows():
                    clusters[key]["exact"] += matched

                at = l2.group_by(["cluster_key", "time_exchange"]).agg(pl.col("price").mean().alias("p2"))
                bt = l4.group_by(["cluster_key", "time_exchange"]).agg(pl.col("price").mean().alias("p4"))
                for key, count in at.group_by("cluster_key").len().iter_rows():
                    clusters[key]["t2"] += count
                for key, count in bt.group_by("cluster_key").len().iter_rows():
                    clusters[key]["t4"] += count
                aligned = at.join(bt, on=["cluster_key", "time_exchange"], how="inner").with_columns(
                    ((pl.col("p4") - pl.col("p2")).abs() / pl.col("p2") * 10_000.0).alias("abs_diff_bps")
                )
                for row in aligned.group_by("cluster_key").agg(
                    pl.len().alias("aligned_n"), pl.col("abs_diff_bps").sum().alias("price_diff_sum")
                ).iter_rows(named=True):
                    clusters[row["cluster_key"]]["aligned_n"] += row["aligned_n"]
                    clusters[row["cluster_key"]]["price_diff_sum"] += row["price_diff_sum"]
            else:
                for key, count in l2.select("cluster_key", "time_exchange").unique().group_by("cluster_key").len().iter_rows():
                    clusters[key]["t2"] += count
                for key, count in l4.select("cluster_key", "time_exchange").unique().group_by("cluster_key").len().iter_rows():
                    clusters[key]["t4"] += count
        output["markets"][market] = [dict({"cluster_key": key}, **values) for key, values in sorted(clusters.items())]
        print(f"overlap {market}: clusters={len(clusters)}", flush=True)
    OVERLAP_PATH.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")


def agg_ratio_ci(rows: list[dict[str, object]], num: str, den: str, seed: int = 0) -> dict[str, object]:
    payload = [(float(r.get(num, 0) or 0), float(r.get(den, 0) or 0)) for r in rows if float(r.get(den, 0) or 0) > 0]
    total_num = sum(x for x, _ in payload)
    total_den = sum(x for _, x in payload)
    point = None if total_den == 0 else total_num / total_den
    G = len(payload)
    result = {"point": point, "low": None, "high": None, "n": int(total_den), "G": G, "low_cluster": G < MIN_CLUSTERS}
    if point is None or G < MIN_CLUSTERS:
        return result
    rng = random.Random(seed)
    draws = []
    for _ in range(N_RESAMPLES):
        sample = [payload[rng.randrange(G)] for _ in range(G)]
        d = sum(x[1] for x in sample)
        draws.append(sum(x[0] for x in sample) / d)
    draws.sort()
    result["low"] = percentile(draws, 0.025)
    result["high"] = percentile(draws, 0.975)
    return result


def bootstrap_custom(rows: list[dict[str, object]], fn, n_fn, seed: int = 0) -> dict[str, object]:
    rows = [r for r in rows if any(float(v or 0) for k, v in r.items() if k != "cluster_key")]
    point = fn(rows)
    G = len(rows)
    result = {"point": point, "low": None, "high": None, "n": int(n_fn(rows)), "G": G, "low_cluster": G < MIN_CLUSTERS}
    if point is None or G < MIN_CLUSTERS:
        return result
    rng = random.Random(seed)
    draws = []
    for _ in range(N_RESAMPLES):
        value = fn([rows[rng.randrange(G)] for _ in range(G)])
        if value is not None:
            draws.append(value)
    draws.sort()
    result["low"] = percentile(draws, 0.025)
    result["high"] = percentile(draws, 0.975)
    return result


def percentile(values: list[float], p: float) -> float:
    pos = (len(values) - 1) * p
    lo = math.floor(pos)
    hi = min(lo + 1, len(values) - 1)
    w = pos - lo
    return values[lo] * (1 - w) + values[hi] * w


def fmt_ci(result: dict[str, object], scale: float = 1.0, digits: int = 3, suffix: str = "") -> str:
    if result["point"] is None:
        return f"insufficient evidence (n={result['n']}, G={result['G']}; 95% CI undefined)"
    point = float(result["point"]) * scale
    if result["low"] is None or result["high"] is None:
        return f"{point:.{digits}f}{suffix} (n={result['n']}, G={result['G']}; 95% CI undefined—insufficient evidence)"
    low = float(result["low"]) * scale
    high = float(result["high"]) * scale
    return f"{point:.{digits}f}{suffix} (n={result['n']}, G={result['G']}; 95% CI [{low:.{digits}f}, {high:.{digits}f}]{suffix})"


def summary_lookup(frame: pl.DataFrame) -> dict[tuple[object, ...], dict[str, object]]:
    dims = [c for c in frame.columns if c not in {"horizon", "point_estimate_bps", "ci_low_bps", "ci_high_bps", "n", "G", "low_cluster", "staleness_rate_30s"}]
    return {
        tuple(row[d] for d in dims): {
            "point": row["point_estimate_bps"], "low": row["ci_low_bps"], "high": row["ci_high_bps"],
            "n": row["n"], "G": row["G"], "low_cluster": row["low_cluster"],
        }
        for row in frame.iter_rows(named=True)
    }


def load_day_stats() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    census: list[dict[str, object]] = []
    latency: list[dict[str, object]] = []
    for path in sorted(STATS.glob("*.json")):
        item = json.loads(path.read_text())
        census.extend(item["census"])
        latency.extend(item["latency"])
    return census, latency


def overlap_metric(rows: list[dict[str, object]], kind: str) -> dict[str, object]:
    if kind == "count":
        fn = lambda xs: (min(sum(float(r.get("l2", 0)) for r in xs), sum(float(r.get("l4", 0)) for r in xs)) / max(sum(float(r.get("l2", 0)) for r in xs), sum(float(r.get("l4", 0)) for r in xs))) if max(sum(float(r.get("l2", 0)) for r in xs), sum(float(r.get("l4", 0)) for r in xs)) else None
        nf = lambda xs: max(sum(float(r.get("l2", 0)) for r in xs), sum(float(r.get("l4", 0)) for r in xs))
    elif kind == "exact":
        fn = lambda xs: sum(float(r.get("exact", 0)) for r in xs) / max(sum(float(r.get("l2", 0)) for r in xs), sum(float(r.get("l4", 0)) for r in xs)) if max(sum(float(r.get("l2", 0)) for r in xs), sum(float(r.get("l4", 0)) for r in xs)) else None
        nf = lambda xs: max(sum(float(r.get("l2", 0)) for r in xs), sum(float(r.get("l4", 0)) for r in xs))
    elif kind == "time":
        fn = lambda xs: sum(float(r.get("aligned_n", 0)) for r in xs) / max(sum(float(r.get("t2", 0)) for r in xs), sum(float(r.get("t4", 0)) for r in xs)) if max(sum(float(r.get("t2", 0)) for r in xs), sum(float(r.get("t4", 0)) for r in xs)) else None
        nf = lambda xs: max(sum(float(r.get("t2", 0)) for r in xs), sum(float(r.get("t4", 0)) for r in xs))
    else:
        fn = lambda xs: sum(float(r.get("price_diff_sum", 0)) for r in xs) / sum(float(r.get("aligned_n", 0)) for r in xs) if sum(float(r.get("aligned_n", 0)) for r in xs) else None
        nf = lambda xs: sum(float(r.get("aligned_n", 0)) for r in xs)
    return bootstrap_custom(rows, fn, nf)


def run_report() -> None:
    if not FILLS_PATH.exists() or not OVERLAP_PATH.exists():
        raise RuntimeError("fills or overlap artifact absent")
    fills = pl.read_parquet(FILLS_PATH)
    if fills.is_empty():
        raise RuntimeError("BLOCKER_SYSTEMIC_EMPTY_FILLS: final fill parquet is empty")
    primary = primary_summary(fills, n_resamples=N_RESAMPLES, seed=0, min_clusters=MIN_CLUSTERS)
    horizons = {
        h: secondary_summary(fills, by=["market", "segment"], horizon=h, n_resamples=N_RESAMPLES, seed=0, min_clusters=MIN_CLUSTERS)
        for h in HORIZONS_SECONDS
    }
    by_side = secondary_summary(fills, by=["market", "segment", "side"], n_resamples=N_RESAMPLES, seed=0, min_clusters=MIN_CLUSTERS)
    by_hour = secondary_summary(fills, by=["market", "segment", "hour_of_day"], n_resamples=N_RESAMPLES, seed=0, min_clusters=MIN_CLUSTERS)
    by_size = secondary_summary(fills, by=["market", "segment", "size_bucket"], n_resamples=N_RESAMPLES, seed=0, min_clusters=MIN_CLUSTERS)
    census_rows, latency_rows = load_day_stats()
    overlap = json.loads(OVERLAP_PATH.read_text())["markets"]
    funding_meta = json.loads(FUNDING_META.read_text())["markets"]
    run_meta = json.loads(RUN_META.read_text())
    day_items = [json.loads(path.read_text()) for path in sorted(STATS.glob("*.json"))]
    sanitation_totals = {
        key: sum(int(item.get(key, 0)) for item in day_items)
        for key in [
            "book_was_unsorted",
            "pre_snapshot_events_trimmed",
            "rotated_snapshot_rows_dropped",
            "orphan_subs_dropped",
            "oversize_subs_clamped",
            "crossed_l1_rows_invalidated",
        ]
    }
    overlap_document = json.loads(OVERLAP_PATH.read_text())
    skipped_overlap_files = overlap_document.get("skipped_files", [])

    lines = [
        "# Study 1: off-hours markout measurements",
        "",
        "Run date: 2026-07-10. Data window: 2026-03-11 through 2026-06-08. Results below are measurements and interval-comparison statuses only.",
        "",
        "## Method and run census",
        "",
        f"The L2 run processed n={run_meta['market_days_processed']} market-days and wrote n={run_meta['total_fills']} simulated fills. Each market-day was processed independently with projected columns. The requested user-scoped systemd manager was unreachable in the execution container; the run used a hard 6 GiB virtual-address-space limit (`prlimit --as=6442450944`).",
        "",
        f"Feed sanitation census: n={sanitation_totals['book_was_unsorted']} non-monotonic market-day books were stable-sorted; n={sanitation_totals['pre_snapshot_events_trimmed']} pre-first-snapshot events and n={sanitation_totals['rotated_snapshot_rows_dropped']} rotated snapshot rows were excluded; n={sanitation_totals['orphan_subs_dropped']} orphan deep-level SUB events were dropped; n={sanitation_totals['oversize_subs_clamped']} oversize SUB events were clamped to level removal; n={sanitation_totals['crossed_l1_rows_invalidated']} crossed reconstructed L1 rows were invalidated to missing state. These are observed row counts, not sampled estimates.",
        "",
        "Census definitions: spread is `(ask-bid)/mid` in bps; depth is combined displayed bid-plus-ask touch size in base units; uptime is the two-sided-valid fraction of reconstructed L1 update rows. These are L1-update-row-weighted observations. Staleness is the fraction of simulated fills whose 30s markout was excluded by the 60s quote-age rule. Intervals resample whole market × UTC six-hour clusters with 2,000 draws; `G<5` has an undefined interval and is labeled insufficient evidence.",
        "",
        "| Market | Segment | Spread bps | Touch depth units | Two-sided uptime | 30s staleness |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for market in MARKETS:
        for segment in SEGMENTS:
            rows = [r for r in census_rows if r["market"] == market and r["segment"] == segment]
            fill_group = fills.filter((pl.col("market") == market) & (pl.col("segment") == segment))
            stale_rows = [
                {"cluster_key": row[0], "num": row[1], "den": row[2]}
                for row in fill_group.group_by("cluster_key").agg(
                    pl.col("stale_30s").cast(pl.Float64).sum().alias("num"), pl.len().alias("den")
                ).iter_rows()
            ]
            lines.append(
                f"| {market} | {segment} | {fmt_ci(agg_ratio_ci(rows, 'spread_num', 'spread_den'))} | {fmt_ci(agg_ratio_ci(rows, 'depth_num', 'depth_den'))} | {fmt_ci(agg_ratio_ci(rows, 'uptime_num', 'uptime_den'), scale=100, suffix='%')} | {fmt_ci(agg_ratio_ci(stale_rows, 'num', 'den'), scale=100, suffix='%')} |"
            )

    lines += ["", "## Net markouts by horizon", "", "Every cell is pooled net bps with n, cluster count G, and a cluster-bootstrap 95% CI. Null markouts, including stale observations, are excluded.", "", "| Market | Segment | 1s | 5s | 30s | 2m | 10m |", "|---|---|---:|---:|---:|---:|---:|"]
    lookups = {h: summary_lookup(frame) for h, frame in horizons.items()}
    absent = {"point": None, "low": None, "high": None, "n": 0, "G": 0, "low_cluster": True}
    for market in MARKETS:
        for segment in SEGMENTS:
            cells = [fmt_ci(lookups[h].get((market, segment), absent)) for h in HORIZONS_SECONDS]
            lines.append(f"| {market} | {segment} | " + " | ".join(cells) + " |")

    lines += ["", "## Primary 30s CI-separation status", "", "The numeric comparison is `off-hours lower CI > RTH upper CI`. Undefined intervals are insufficient evidence and are never counted as separation.", "", "| Market | Comparison | RTH net bps | Other-segment net bps | CI-separation status |", "|---|---|---:|---:|---|"]
    p = summary_lookup(primary)
    for market in MARKETS:
        rth = p.get((market, "RTH"), absent)
        for segment in ["off-hours-weekday", "weekend"]:
            other = p.get((market, segment), absent)
            if rth["low"] is None or other["low"] is None:
                status = "insufficient evidence (at least one 95% CI undefined)"
            else:
                status = "yes" if float(other["low"]) > float(rth["high"]) else "no"
            lines.append(f"| {market} | {segment} vs RTH | {fmt_ci(rth)} | {fmt_ci(other)} | {status} |")

    def append_secondary(title: str, frame: pl.DataFrame, dims: list[str]) -> None:
        lines.extend(["", f"## Secondary: {title}", "", "| " + " | ".join(dims) + " | 30s net bps |", "|" + "---|" * (len(dims) + 1)])
        for row in frame.sort(dims).iter_rows(named=True):
            result = {"point": row["point_estimate_bps"], "low": row["ci_low_bps"], "high": row["ci_high_bps"], "n": row["n"], "G": row["G"], "low_cluster": row["low_cluster"]}
            lines.append("| " + " | ".join(str(row[d]) for d in dims) + f" | {fmt_ci(result)} |")

    append_secondary("side", by_side, ["market", "segment", "side"])
    append_secondary("UTC hour of day", by_hour, ["market", "segment", "hour_of_day"])
    append_secondary("filling-print size bucket", by_size, ["market", "segment", "size_bucket"])

    lines += ["", "## Era-overlap cross-validation", "", "Window: 2026-05-08 through 2026-06-08. Count agreement is `min(L2,L4)/max(L2,L4)`. Exact-event agreement uses timestamp, price, and size. Timestamp alignment compares unique exchange timestamps; aligned-price difference is mean absolute bps at shared timestamps. All interval metrics resample UTC six-hour clusters.", "", "| Market | Trade counts | Count agreement | Exact-event agreement | Timestamp alignment | Aligned price abs diff bps |", "|---|---:|---:|---:|---:|---:|"]
    for market in MARKETS:
        rows = overlap.get(market, [])
        n2 = int(sum(float(r.get("l2", 0)) for r in rows))
        n4 = int(sum(float(r.get("l4", 0)) for r in rows))
        lines.append(f"| {market} | L2 n={n2}; L4 n={n4} | {fmt_ci(overlap_metric(rows, 'count'), scale=100, suffix='%')} | {fmt_ci(overlap_metric(rows, 'exact'), scale=100, suffix='%')} | {fmt_ci(overlap_metric(rows, 'time'), scale=100, suffix='%')} | {fmt_ci(overlap_metric(rows, 'price'))} |")
    if skipped_overlap_files:
        lines += ["", "Overlap input caveat: the following on-disk file failed gzip decompression and was excluded:"]
        lines.extend(f"- `{item}`" for item in skipped_overlap_files)

    lines += ["", "## Exchange-to-CoinAPI latency context", "", "Latency uses L2 trade rows and `time_coinapi-time_exchange`. Each item includes n, G, and a six-hour-cluster-bootstrap interval.", ""]
    lines.append(f"- Mean milliseconds: {fmt_ci(agg_ratio_ci(latency_rows, 'latency_num', 'latency_den'))}")
    for col, label in [("negative_num", "Negative"), ("le500_num", "At or below 500 ms"), ("le1000_num", "At or below 1,000 ms"), ("le5000_num", "At or below 5,000 ms")]:
        lines.append(f"- {label}: {fmt_ci(agg_ratio_ci(latency_rows, col, 'latency_den'), scale=100, suffix='%')}")

    lines += ["", "## Funding fetch", "", "The public Hyperliquid funding-history REST endpoint was queried at no more than one request per second. Funding is applied as the latest known hourly rate and held fixed through each short markout horizon.", "", "| Market | API rows (n) | REST calls (n) | Explicit zero series | Initial zero prefix |", "|---|---:|---:|---|---|"]
    for market in MARKETS:
        item = funding_meta[market]
        lines.append(f"| {market} | {item['api_rows_in_window']} | {item['calls']} | {str(item['zero_series']).lower()} | {str(item['zero_prefix']).lower()} |")

    lines += [
        "", "## Biases and assumptions", "",
        "- The passive-fill rule is an optimistic upper bound because prints do not reveal cancellations ahead, hidden liquidity, exact priority, or the order's effect on subsequent flow.",
        "- The maker fee is assumed at 1.5 bps. Funding uses the latest REST hourly rate known at fill and holds it fixed across the horizon.",
        "- One-sided or invalid L1 rows are skipped for microprice and fill eligibility. Trades sharing an exact timestamp with an L1 change are dropped because within-timestamp ordering is unknown (ADV-3).",
        "- Confidence intervals use a pooled nonparametric bootstrap of market × UTC six-hour clusters, 2,000 resamples, seed 0, and minimum G=5. The quote-age ceiling is 60 seconds. Fee, age ceiling, resample count, seed, cluster length, and minimum cluster count are operator-tunable.",
        "- The L2 book is level-aggregated; queue-ahead is displayed touch size at join. The optional L4 quotes-as-L1 run was not executed, so no top-of-book queue-ahead results are mixed into the L2 primary.",
        "- Stable sorting and the feed sanitation counts above address rotated daily chunks and depth-truncated snapshot updates without using future state. Invalid/crossed rows reset eligibility rather than generating a fill.",
        "",
        "## Artifacts and follow-ups", "",
        "- Per-fill L2 artifact: `data/reports/study1_fills_l2.parquet`.",
        "- Funding artifact: `data/reports/study1_funding.parquet`.",
        "- Optional follow-up: run L4 quotes-as-L1 markouts and label their queue-ahead model as top-of-book/coarser.",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["funding", "l2", "overlap", "report"], required=True)
    args = parser.parse_args()
    {"funding": fetch_funding, "l2": run_l2, "overlap": run_overlap, "report": run_report}[args.phase]()


if __name__ == "__main__":
    main()
