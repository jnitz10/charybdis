"""Plan, pull, and analyze proxy-tagged Study-2 forced-flow windows."""

from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
import io
import json
import math
import os
from pathlib import Path
from typing import Iterable, Sequence

import polars as pl

from charybdis.book import sample_l4_depth
from charybdis.calendars import label_krx
from charybdis.ffs3 import (
    FlatFilesS3Client,
    ObjectInfo,
    SpendMeter,
    build_manifest,
    execute_manifest,
)
from charybdis.loaders import (
    parse_flat_file_key,
    scan_book_events,
    scan_oracle_prices,
    scan_quotes,
    scan_trades,
)
from charybdis.markout import (
    HORIZONS_SECONDS,
    build_fill_markouts,
    cluster_bootstrap_ci,
)
from charybdis.study2 import (
    PROXY_LABEL,
    MergedEventWindow,
    PullWindowPair,
    Window,
    compute_cascade_anatomy,
    hours_touched,
    match_baseline_windows,
    merge_event_windows,
    select_window_pairs_within_budget,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
REPORTS = DATA / "reports"
EVENTS_PATH = REPORTS / "forced_flow_events_proxy.parquet"
SPEND_PATH = DATA / "spend.json"
PLAN_PATH = DATA / "study2_t7_plan.json"
MANIFEST_PATH = DATA / "study2_t7_book_manifest.json"
LISTING_PATH = DATA / "study2_t7_book_listing.json"
DRY_RUN_PATH = DATA / "study2_t7_dry_run.log"
DOWNLOAD_LOG_PATH = DATA / "study2_t7_download.log"
WINDOWS_PATH = REPORTS / "study2_t7_windows_proxy.parquet"
ANATOMY_PATH = REPORTS / "forced_flow_event_anatomy_proxy.parquet"
FILLS_PATH = REPORTS / "forced_flow_vs_baseline_fills_proxy.parquet"
MARKOUT_PATH = REPORTS / "forced_flow_vs_baseline_markout_proxy.parquet"
QUOTE_COVERAGE_PATH = REPORTS / "forced_flow_quote_coverage_proxy.parquet"
CONDITIONING_PATH = REPORTS / "forced_flow_conditioning_events_proxy.parquet"
FUNDING_SUMMARY_PATH = REPORTS / "forced_flow_conditioning_funding_proxy.parquet"
ORACLE_SUMMARY_PATH = REPORTS / "forced_flow_conditioning_oracle_krx_proxy.parquet"
OI_PATH = REPORTS / "forced_flow_conditioning_oi_daily_proxy.parquet"
ANALYSIS_META_PATH = REPORTS / "forced_flow_analysis_meta_proxy.json"
DEPTH_SAMPLES_PATH = REPORTS / "study2_depth_samples_proxy.parquet"
FUNDING_PATH = DATA / "study2_funding.parquet"

TARGETS = ("SKHX", "SMSN")
BOOK_COLUMNS = (
    "time_exchange",
    "update_type",
    "is_buy",
    "entry_px",
    "entry_sx",
    "order_id",
    "is_trigger",
    "order_type",
    "hl4_status",
)
QUOTE_COLUMNS = ("time_exchange", "ask_px", "ask_sx", "bid_px", "bid_sx")
TRADE_COLUMNS = ("time_exchange", "price", "base_amount")
ORACLE_COLUMNS = ("time_exchange", "coin_id", "update_class", "mark_px")


def _book_columns_for_schema(available: Iterable[str]) -> tuple[str, ...]:
    """Project live-order fields present in each historical L4 schema era."""

    names = set(available)
    required = BOOK_COLUMNS[:6]
    missing = [name for name in required if name not in names]
    if missing:
        raise ValueError(f"book schema missing required columns: {missing}")
    return tuple(name for name in BOOK_COLUMNS if name in names)


def _read_coinapi_key() -> str:
    value = os.environ.get("COINAPI_API_KEY")
    if value:
        return value
    env_path = ROOT / ".env"
    with env_path.open("r", encoding="utf-8") as source:
        for line in source:
            if line.startswith("COINAPI_API_KEY="):
                value = line.split("=", 1)[1].strip().strip("'\"")
                if value:
                    return value
                break
    raise RuntimeError("COINAPI_API_KEY is not set")


def _inventory(dataset: str, targets: Sequence[str] = TARGETS) -> dict[tuple[str, str], Path]:
    wanted = set(targets)
    found: dict[tuple[str, str], Path] = {}
    for path in sorted((DATA / f"T-{dataset}").rglob("*.csv.gz")):
        try:
            key = parse_flat_file_key(path)
        except ValueError:
            continue
        market = key.coin.rsplit(":", 1)[-1]
        if key.era == "l4" and market in wanted:
            item = (market, key.partition)
            if item in found:
                raise RuntimeError(f"duplicate {dataset} object for {item}")
            found[item] = path
    return found


def _coverage_from_quotes() -> dict[str, Window]:
    inventory = _inventory("QUOTES")
    result: dict[str, Window] = {}
    for market in TARGETS:
        hours = sorted(
            datetime.strptime(partition, "%Y%m%d%H")
            for (found_market, partition) in inventory
            if found_market == market
        )
        if not hours:
            raise RuntimeError(f"no local quote coverage for {market}")
        result[market] = Window(hours[0], hours[-1] + timedelta(hours=1))
    return result


def _event_rows_with_ids(events: pl.DataFrame) -> pl.DataFrame:
    ordered = events.sort(["market", "start_time", "end_time"])
    rows = []
    for ordinal, row in enumerate(ordered.iter_rows(named=True), start=1):
        rows.append({**row, "event_id": f"{row['market']}-{ordinal:06d}"})
    return pl.DataFrame(rows).with_columns(
        pl.col("start_time").cast(pl.Datetime("ns")),
        pl.col("end_time").cast(pl.Datetime("ns")),
    )


def _list_book_catalog(
    needed: set[tuple[str, datetime]],
) -> tuple[list[ObjectInfo], list[tuple[str, datetime]]]:
    client = FlatFilesS3Client(_read_coinapi_key())

    needed_by_hour: dict[datetime, set[str]] = {}
    for market, hour in needed:
        needed_by_hour.setdefault(hour, set()).add(market)

    def list_one(hour: datetime, markets: set[str]) -> dict[str, ObjectInfo]:
        prefix = (
            f"T-LIMITBOOK_FULL/D-{hour:%Y%m%d%H}/E-HYPERLIQUIDL4/"
        )
        matches: dict[str, ObjectInfo] = {}
        for item in client.list_with_sizes(prefix):
            try:
                key = parse_flat_file_key(item.key)
            except ValueError:
                continue
            found_market = key.coin.rsplit(":", 1)[-1]
            if key.dataset != "LIMITBOOK_FULL" or key.exchange_id != "HYPERLIQUIDL4":
                continue
            if found_market in markets:
                if found_market in matches:
                    raise RuntimeError(
                        f"multiple book objects for {found_market} {hour}"
                    )
                matches[found_market] = item
        return matches

    selected: list[ObjectInfo] = []
    missing: list[tuple[str, datetime]] = []
    ordered_hours = sorted(needed_by_hour)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(list_one, hour, markets): (hour, markets)
            for hour, markets in needed_by_hour.items()
        }
        completed = 0
        for future in as_completed(futures):
            hour, markets = futures[future]
            matches = future.result()
            selected.extend(matches.values())
            missing.extend(
                (market, hour) for market in sorted(markets - set(matches))
            )
            completed += 1
            if completed % 100 == 0 or completed == len(ordered_hours):
                print(
                    f"LIST {completed}/{len(ordered_hours)} "
                    f"found={len(selected)} missing={len(missing)}",
                    flush=True,
                )
    return sorted(selected, key=lambda item: item.key), sorted(missing)


def _pair_keys(
    pair: PullWindowPair,
    catalog_by_hour: dict[tuple[str, datetime], str],
) -> tuple[str, ...]:
    windows = [pair.event]
    if pair.baseline is not None:
        windows.append(pair.baseline)
    return tuple(
        sorted(
            {
                catalog_by_hour[(pair.market, hour)]
                for window in windows
                for hour in hours_touched(window)
                if (pair.market, hour) in catalog_by_hour
            }
        )
    )


def _window_row(
    pair: PullWindowPair,
    window_type: str,
    window: Window,
    status: str,
) -> dict[str, object]:
    return {
        "pair_id": pair.pair_id,
        "market": pair.market,
        "window_type": window_type,
        "window_start": window.start,
        "window_end": window.end,
        "burst_strength": pair.burst_strength,
        "event_count": len(pair.event_ids),
        "status": status,
        "tag_label": PROXY_LABEL,
    }


def plan_pull() -> dict[str, object]:
    REPORTS.mkdir(parents=True, exist_ok=True)
    events = pl.read_parquet(EVENTS_PATH)
    merged = merge_event_windows(events)
    matched, unmatched = match_baseline_windows(
        merged,
        events,
        coverage=_coverage_from_quotes(),
    )
    all_pairs = [*matched]
    for item in unmatched:
        all_pairs.append(
            PullWindowPair(
                pair_id=item.pair_id,
                market=item.market,
                event=item.window,
                baseline=None,
                burst_strength=item.burst_strength,
                object_keys=(),
                event_ids=item.event_ids,
            )
        )

    needed = {
        (pair.market, hour)
        for pair in all_pairs
        for window in (pair.event, pair.baseline)
        if window is not None
        for hour in hours_touched(window)
    }
    listed, missing = _list_book_catalog(needed)
    listing_payload = {
        "listed_at_utc": datetime.now(UTC).isoformat(),
        "objects": [{"key": item.key, "size": item.size} for item in listed],
        "missing_market_hours": [
            {"market": market, "hour": hour.isoformat()} for market, hour in missing
        ],
    }
    LISTING_PATH.write_text(json.dumps(listing_payload, indent=2, sort_keys=True) + "\n")

    catalog_by_key = {item.key: item for item in listed}
    catalog_by_hour: dict[tuple[str, datetime], str] = {}
    for item in listed:
        key = parse_flat_file_key(item.key)
        market = key.coin.rsplit(":", 1)[-1]
        catalog_by_hour[(market, datetime.strptime(key.partition, "%Y%m%d%H"))] = item.key
    all_pairs = [
        replace(pair, object_keys=_pair_keys(pair, catalog_by_hour))
        for pair in all_pairs
    ]
    meter = SpendMeter(SPEND_PATH)
    billing_day = datetime.now(UTC).date().isoformat()

    def manifest_for_keys(keys: Iterable[str]):
        objects = [catalog_by_key[key] for key in sorted(set(keys))]
        return build_manifest(objects, meter, billing_day=billing_day, data_root=DATA)

    all_manifest = manifest_for_keys(
        key for pair in all_pairs for key in pair.object_keys
    )
    full_output = io.StringIO()
    execute_manifest(
        FlatFilesS3Client(_read_coinapi_key()),
        all_manifest,
        meter,
        data_root=DATA,
        dry_run=True,
        output=full_output,
    )
    full_text = full_output.getvalue()
    selection = select_window_pairs_within_budget(
        all_pairs,
        cost_for_keys=lambda keys: manifest_for_keys(keys).estimated_cost_usd,
        budget_usd=40.0,
    )
    if not selection.selected_pairs:
        strongest = max(all_pairs, key=lambda pair: pair.burst_strength)
        strongest_day = strongest.event.start.date()
        same_market_day = [
            pair
            for pair in all_pairs
            if pair.market == strongest.market and pair.event.start.date() == strongest_day
        ]
        day_cost = manifest_for_keys(
            key for pair in same_market_day for key in pair.object_keys
        ).estimated_cost_usd
        stop = {
            "stop": True,
            "reason": "single strongest market-day exceeds T7 $40 pull budget",
            "market": strongest.market,
            "day": strongest_day.isoformat(),
            "estimated_cost_usd": day_cost,
        }
        PLAN_PATH.write_text(json.dumps(stop, indent=2, sort_keys=True) + "\n")
        raise RuntimeError(json.dumps(stop, sort_keys=True))

    approved_manifest = manifest_for_keys(
        key for pair in selection.selected_pairs for key in pair.object_keys
    )
    approved_output = io.StringIO()
    execute_manifest(
        FlatFilesS3Client(_read_coinapi_key()),
        approved_manifest,
        meter,
        data_root=DATA,
        dry_run=True,
        output=approved_output,
    )
    approved_text = approved_output.getvalue()
    DRY_RUN_PATH.write_text(
        "FULL PLAN\n" + full_text + "\nAPPROVED PLAN\n" + approved_text,
        encoding="utf-8",
    )
    print(full_text.splitlines()[0], flush=True)
    if selection.downscoped:
        print(approved_text.splitlines()[0], flush=True)

    selected_ids = {pair.pair_id for pair in selection.selected_pairs}
    window_rows: list[dict[str, object]] = []
    for pair in all_pairs:
        status = "pulled-plan" if pair.pair_id in selected_ids else "budget-dropped"
        window_rows.append(_window_row(pair, "event", pair.event, status))
        if pair.baseline is not None:
            window_rows.append(_window_row(pair, "baseline", pair.baseline, status))
    pl.DataFrame(window_rows).sort(["market", "window_start", "window_type"]).write_parquet(
        WINDOWS_PATH
    )
    MANIFEST_PATH.write_text(
        json.dumps(
            {
                "billing_day": billing_day,
                "objects": [
                    {"key": item.key, "size": item.size}
                    for item in (
                        catalog_by_key[file.key] for file in approved_manifest.files
                    )
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    dropped_event_count = sum(len(pair.event_ids) for pair in selection.dropped_pairs)
    plan = {
        "stop": False,
        "tag_label": PROXY_LABEL,
        "baseline_matching_rule": (
            "same exact UTC clock-time and duration; nearest calendar day, earlier "
            "on ties; no overlap with any event ±30m window or prior baseline"
        ),
        "event_windows_planned": len(merged),
        "baseline_windows_planned": len(matched),
        "unmatched_baseline_windows": len(unmatched),
        "event_windows_approved": len(selection.selected_pairs),
        "baseline_windows_approved": sum(
            pair.baseline is not None for pair in selection.selected_pairs
        ),
        "raw_events_planned": events.height,
        "raw_events_dropped": dropped_event_count,
        "window_pairs_dropped": len(selection.dropped_pairs),
        "downscoped": selection.downscoped,
        "coverage_cut_reason": selection.coverage_cut_reason,
        "full_dry_run_line": full_text.splitlines()[0],
        "approved_dry_run_line": approved_text.splitlines()[0],
        "approved_cost_usd": approved_manifest.estimated_cost_usd,
        "approved_bytes": sum(file.size for file in approved_manifest.files),
        "approved_files": len(approved_manifest.files),
        "missing_market_hours": len(missing),
        "spend_before_pull_usd": meter.running_cost_usd,
        "selected_pair_ids": [pair.pair_id for pair in selection.selected_pairs],
        "dropped_pair_ids": [pair.pair_id for pair in selection.dropped_pairs],
    }
    PLAN_PATH.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    print(json.dumps(plan, sort_keys=True), flush=True)
    return plan


def download_pull() -> dict[str, object]:
    plan = json.loads(PLAN_PATH.read_text())
    if plan.get("stop"):
        raise RuntimeError(f"pull plan is stopped: {plan}")
    payload = json.loads(MANIFEST_PATH.read_text())
    objects = [ObjectInfo(key=item["key"], size=int(item["size"])) for item in payload["objects"]]
    meter = SpendMeter(SPEND_PATH)
    before = meter.running_cost_usd
    manifest = build_manifest(
        objects,
        meter,
        billing_day=payload["billing_day"],
        data_root=DATA,
    )
    if manifest.estimated_cost_usd > 40.0 + 1e-9:
        raise RuntimeError("approved T7 manifest now exceeds $40; refusing GET")
    with DOWNLOAD_LOG_PATH.open("w", encoding="utf-8") as output:
        result = execute_manifest(
            FlatFilesS3Client(_read_coinapi_key()),
            manifest,
            meter,
            data_root=DATA,
            workers=8,
            output=output,
        )
    after = meter.running_cost_usd
    summary = {
        "downloaded": result.downloaded,
        "skipped": result.skipped,
        "paused": result.paused,
        "final_pulled_usd": after - before,
        "spend_running_total_usd": after,
    }
    plan.update(summary)
    PLAN_PATH.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True), flush=True)
    return summary


def _load_quotes(paths: Iterable[Path], start: datetime, end: datetime) -> pl.DataFrame:
    return _load_quote_rows(paths, start, end).filter(
        pl.col("best_bid_px") <= pl.col("best_ask_px")
    )


def _load_quote_rows(paths: Iterable[Path], start: datetime, end: datetime) -> pl.DataFrame:
    parts = []
    for path in sorted(set(paths)):
        try:
            parts.append(
                scan_quotes(path, columns=QUOTE_COLUMNS)
                .filter(
                    (pl.col("time_exchange") >= start)
                    & (pl.col("time_exchange") <= end)
                )
                .collect(engine="streaming")
            )
        except OSError as error:
            print(f"SKIP corrupt quote {path.relative_to(ROOT)}: {error}", flush=True)
    if not parts:
        return pl.DataFrame(
            schema={
                "time_exchange": pl.Datetime("ns"),
                "best_bid_px": pl.Float64,
                "best_bid_sx": pl.Float64,
                "best_ask_px": pl.Float64,
                "best_ask_sx": pl.Float64,
            }
        )
    return (
        pl.concat(parts, how="vertical_relaxed")
        .sort("time_exchange", maintain_order=True)
        .unique(subset="time_exchange", keep="last", maintain_order=True)
        .rename(
            {
                "bid_px": "best_bid_px",
                "bid_sx": "best_bid_sx",
                "ask_px": "best_ask_px",
                "ask_sx": "best_ask_sx",
            }
        )
    )


def _load_trades(paths: Iterable[Path], start: datetime, end: datetime) -> pl.DataFrame:
    parts = []
    for path in sorted(set(paths)):
        try:
            parts.append(
                scan_trades(path, columns=TRADE_COLUMNS)
                .filter(
                    (pl.col("time_exchange") >= start)
                    & (pl.col("time_exchange") <= end)
                )
                .collect(engine="streaming")
            )
        except OSError as error:
            print(f"SKIP corrupt trade {path.relative_to(ROOT)}: {error}", flush=True)
    if not parts:
        return pl.DataFrame(
            schema={
                "time_exchange": pl.Datetime("ns"),
                "price": pl.Float64,
                "base_amount": pl.Float64,
            }
        )
    return pl.concat(parts, how="vertical_relaxed").sort(
        "time_exchange", maintain_order=True
    )


def _paths_for_window(
    inventory: dict[tuple[str, str], Path], market: str, window: Window
) -> list[Path]:
    return [
        inventory[(market, hour.strftime("%Y%m%d%H"))]
        for hour in hours_touched(window)
        if (market, hour.strftime("%Y%m%d%H")) in inventory
    ]


def _funding_frame() -> pl.DataFrame:
    return (
        pl.scan_parquet(FUNDING_PATH)
        .filter(pl.col("coin").is_in([f"xyz:{market}" for market in TARGETS]))
        .select(
            pl.col("time_utc").dt.replace_time_zone(None).alias("time_exchange"),
            pl.col("coin").str.split(":").list.last().alias("market"),
            pl.col("funding_rate").cast(pl.Float64).alias("hourly_rate"),
        )
        .collect(engine="streaming")
        .sort(["market", "time_exchange"])
    )


def _selected_pairs(plan: dict[str, object]) -> list[PullWindowPair]:
    selected = set(plan["selected_pair_ids"])
    frame = pl.read_parquet(WINDOWS_PATH).filter(
        pl.col("pair_id").is_in(selected) & (pl.col("status") == "pulled-plan")
    )
    pairs: list[PullWindowPair] = []
    for pair_id in sorted(selected):
        rows = frame.filter(pl.col("pair_id") == pair_id)
        event = rows.filter(pl.col("window_type") == "event").row(0, named=True)
        baseline_rows = rows.filter(pl.col("window_type") == "baseline")
        baseline = None
        if baseline_rows.height:
            item = baseline_rows.row(0, named=True)
            baseline = Window(item["window_start"], item["window_end"])
        pairs.append(
            PullWindowPair(
                pair_id=pair_id,
                market=event["market"],
                event=Window(event["window_start"], event["window_end"]),
                baseline=baseline,
                burst_strength=float(event["burst_strength"]),
                object_keys=(),
            )
        )
    return pairs


def _build_depth_samples(events: pl.DataFrame) -> tuple[pl.DataFrame, list[str]]:
    manifest = json.loads(MANIFEST_PATH.read_text())
    book_inventory: dict[tuple[str, str], Path] = {}
    for item in manifest["objects"]:
        key = parse_flat_file_key(item["key"])
        market = key.coin.rsplit(":", 1)[-1]
        book_inventory[(market, key.partition)] = DATA / item["key"]
    pieces: list[pl.DataFrame] = []
    errors: list[str] = []
    grouped = events.with_columns(
        pl.col("start_time").dt.strftime("%Y%m%d%H").alias("partition")
    ).partition_by(["market", "partition"], maintain_order=True)
    for group in grouped:
        market = group["market"][0]
        partition = group["partition"][0]
        path = book_inventory.get((market, partition))
        if path is None or not path.exists():
            errors.append(f"missing book {market} {partition}")
            continue
        book_scan = scan_book_events(path, columns=None)
        columns = _book_columns_for_schema(book_scan.collect_schema().names())
        book = book_scan.select(columns).collect(engine="streaming")
        if not book["time_exchange"].is_sorted():
            book = book.sort("time_exchange", maintain_order=True)
        first_snapshot = book.filter(
            pl.col("update_type").str.to_uppercase() == "SNAPSHOT"
        )["time_exchange"].min()
        if first_snapshot is None:
            errors.append(f"no snapshot {path.relative_to(ROOT)}")
            continue
        book = book.filter(pl.col("time_exchange") >= first_snapshot)
        try:
            sampled = sample_l4_depth(book, group["start_time"].to_list())
        except ValueError as error:
            errors.append(f"{path.relative_to(ROOT)}: {error}")
            continue
        if sampled.height:
            pieces.append(sampled.with_columns(pl.lit(market).alias("market")))
        print(
            f"DEPTH {market} {partition} events={group.height} rows={sampled.height}",
            flush=True,
        )
    if not pieces:
        return pl.DataFrame(), errors
    return pl.concat(pieces, how="vertical_relaxed"), errors


def _event_anatomy(
    events: pl.DataFrame,
    depth: pl.DataFrame,
    quote_inventory: dict[tuple[str, str], Path],
) -> tuple[pl.DataFrame, list[str]]:
    outputs: list[pl.DataFrame] = []
    errors: list[str] = []
    groups = events.with_columns(
        pl.col("start_time").dt.date().alias("event_date")
    ).partition_by(["market", "event_date"], maintain_order=True)
    for group in groups:
        market = group["market"][0]
        start = group["start_time"].min() - timedelta(minutes=1)
        end = group["end_time"].max() + timedelta(minutes=30)
        paths = _paths_for_window(quote_inventory, market, Window(start, end))
        l1 = _load_quotes(paths, start, end)
        market_depth = depth.filter(pl.col("market") == market).join(
            group.select(pl.col("start_time").alias("time_exchange")).unique(),
            on="time_exchange",
            how="inner",
        )
        if l1.is_empty() or market_depth.is_empty():
            errors.append(f"anatomy coverage absent {market} {group['event_date'][0]}")
            continue
        outputs.append(
            compute_cascade_anatomy(
                group.drop("event_date"),
                l1,
                market_depth.drop("market", strict=False),
            )
        )
        print(
            f"ANATOMY {market} {group['event_date'][0]} events={group.height}",
            flush=True,
        )
    return (pl.concat(outputs, how="diagonal_relaxed") if outputs else pl.DataFrame()), errors


def _run_markouts(
    pairs: Sequence[PullWindowPair],
    quote_inventory: dict[tuple[str, str], Path],
    trade_inventory: dict[tuple[str, str], Path],
    funding: pl.DataFrame,
) -> tuple[pl.DataFrame, list[str], pl.DataFrame]:
    parts_dir = REPORTS / "study2_markout_parts_proxy"
    parts_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    part_paths: list[Path] = []
    coverage_rows: list[dict[str, object]] = []
    windows = [
        (pair, kind, window)
        for pair in pairs
        for kind, window in (("forced-flow", pair.event), ("baseline", pair.baseline))
        if window is not None
    ]
    for index, (pair, kind, window) in enumerate(windows, start=1):
        part = parts_dir / f"{pair.pair_id}_{kind}.parquet"
        quote_window = Window(window.start - timedelta(seconds=60), window.end + timedelta(minutes=10))
        raw_quotes = _load_quote_rows(
            _paths_for_window(quote_inventory, pair.market, quote_window),
            quote_window.start,
            quote_window.end,
        )
        crossed_quote_rows = (
            0
            if raw_quotes.is_empty()
            else raw_quotes.filter(
                pl.col("best_bid_px") > pl.col("best_ask_px")
            ).height
        )
        quote_rows = raw_quotes.height
        usable_quote_rows = quote_rows - crossed_quote_rows
        crossed_fraction = (
            None if quote_rows == 0 else crossed_quote_rows / quote_rows
        )
        quotes = raw_quotes.filter(
            pl.col("best_bid_px") <= pl.col("best_ask_px")
        )
        trades = _load_trades(
            _paths_for_window(trade_inventory, pair.market, window),
            window.start,
            window.end,
        )
        dropped_for_crossed = quote_rows > 0 and usable_quote_rows == 0
        produced_fills = False
        if raw_quotes.is_empty() or trades.is_empty():
            errors.append(f"markout coverage absent {pair.pair_id} {kind}")
        elif quotes.is_empty():
            errors.append(f"crossed quote coverage unusable {pair.pair_id} {kind}")
        elif part.exists() and len(pl.scan_parquet(part).collect_schema()):
            produced_fills = (
                pl.scan_parquet(part).select(pl.len()).collect().item() > 0
            )
            if produced_fills:
                part_paths.append(part)
        else:
            fills = build_fill_markouts(
                quotes,
                trades,
                market=pair.market,
                funding=funding,
                horizons=HORIZONS_SECONDS,
            ).with_columns(
                pl.lit(pair.pair_id).alias("pair_id"),
                pl.lit(kind).alias("window_type"),
                pl.lit(PROXY_LABEL).alias("tag_label"),
            )
            fills.write_parquet(part, compression="zstd")
            produced_fills = not fills.is_empty()
            if produced_fills:
                part_paths.append(part)
        coverage_rows.append(
            {
                "pair_id": pair.pair_id,
                "market": pair.market,
                "window_type": kind,
                "window_start": window.start,
                "window_end": window.end,
                "quote_rows": quote_rows,
                "crossed_quote_rows": crossed_quote_rows,
                "crossed_row_fraction": crossed_fraction,
                "usable_quote_rows": usable_quote_rows,
                "dropped_for_crossed_quotes": dropped_for_crossed,
                "trade_rows": trades.height,
                "produced_fills": produced_fills,
                "tag_label": PROXY_LABEL,
            }
        )
        if index % 25 == 0 or index == len(windows):
            print(f"MARKOUT {index}/{len(windows)}", flush=True)
    nonempty = [path for path in part_paths if path.exists() and path.stat().st_size > 0]
    frames = [
        pl.read_parquet(path)
        for path in nonempty
        if len(pl.scan_parquet(path).collect_schema())
    ]
    fills = pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()
    fills = _matched_pair_fills(fills) if not fills.is_empty() else fills
    matched_ids = set() if fills.is_empty() else set(fills["pair_id"].to_list())
    coverage = pl.DataFrame(coverage_rows, infer_schema_length=None).with_columns(
        pl.col("pair_id").is_in(matched_ids).alias("matched_pair")
    )
    return fills, errors, coverage


def _matched_pair_fills(fills: pl.DataFrame) -> pl.DataFrame:
    """Retain only pair ids with nonempty forced-flow and baseline fill legs."""

    required = {"pair_id", "window_type"}
    missing = sorted(required - set(fills.columns))
    if missing:
        raise ValueError(f"markout fills missing required columns: {missing}")
    matched_ids = (
        fills.filter(pl.col("window_type").is_in(["forced-flow", "baseline"]))
        .group_by("pair_id")
        .agg(pl.col("window_type").n_unique().alias("leg_count"))
        .filter(pl.col("leg_count") == 2)["pair_id"]
    )
    return fills.filter(pl.col("pair_id").is_in(matched_ids.to_list()))


def _quote_coverage_summary(coverage: pl.DataFrame) -> dict[str, object]:
    """Summarize crossed-quote attenuation while retaining per-leg diagnostics."""

    usable = coverage.filter(pl.col("usable_quote_rows") > 0)
    first = None if usable.is_empty() else usable["window_start"].min().date().isoformat()
    last = None if usable.is_empty() else usable["window_start"].max().date().isoformat()
    total = coverage.height
    dropped = int(coverage["dropped_for_crossed_quotes"].sum()) if total else 0
    result: dict[str, object] = {
        "first_usable_quote_date": first,
        "last_usable_quote_date": last,
        "window_count": total,
        "crossed_quote_dropped_window_count": dropped,
        "crossed_quote_dropped_window_fraction": None if total == 0 else dropped / total,
    }
    means: dict[str, float | None] = {}
    for window_type, prefix in (("forced-flow", "forced_flow"), ("baseline", "baseline")):
        group = coverage.filter(pl.col("window_type") == window_type)
        group_count = group.height
        group_dropped = (
            int(group["dropped_for_crossed_quotes"].sum()) if group_count else 0
        )
        mean_fraction = (
            None
            if group_count == 0
            else group["crossed_row_fraction"].mean()
        )
        means[prefix] = mean_fraction
        result.update(
            {
                f"{prefix}_window_count": group_count,
                f"{prefix}_crossed_quote_dropped_window_count": group_dropped,
                f"{prefix}_crossed_quote_dropped_window_fraction": (
                    None if group_count == 0 else group_dropped / group_count
                ),
                f"{prefix}_mean_crossed_row_fraction": mean_fraction,
                f"{prefix}_median_crossed_row_fraction": (
                    None
                    if group_count == 0
                    else group["crossed_row_fraction"].median()
                ),
            }
        )
    ff_mean = means["forced_flow"]
    baseline_mean = means["baseline"]
    result["forced_flow_minus_baseline_mean_crossed_row_fraction"] = (
        None
        if ff_mean is None or baseline_mean is None
        else ff_mean - baseline_mean
    )
    return result


def _markout_summary(
    fills: pl.DataFrame, quote_coverage: pl.DataFrame | None = None
) -> pl.DataFrame:
    fills = _matched_pair_fills(fills)
    rows: list[dict[str, object]] = []
    scopes = [(market, fills.filter(pl.col("market") == market)) for market in TARGETS]
    scopes.append(("ALL", fills))
    for market, scope in scopes:
        for window_type in ("forced-flow", "baseline"):
            group = scope.filter(pl.col("window_type") == window_type)
            for horizon in HORIZONS_SECONDS:
                value_col = f"net_markout_{horizon}_bps"
                clean = group.filter(pl.col(value_col).is_not_null())
                ci = None
                if clean.height:
                    ci = cluster_bootstrap_ci(
                        clean,
                        value_col=value_col,
                        cluster_col="cluster_key",
                        n_resamples=2_000,
                        seed=7,
                        min_clusters=5,
                    )
                rows.append(
                    {
                        "market": market,
                        "window_type": window_type,
                        "horizon": horizon,
                        "point_estimate_bps": None if ci is None else ci.point_estimate,
                        "ci_low_bps": None if ci is None else ci.ci_low,
                        "ci_high_bps": None if ci is None else ci.ci_high,
                        "n": 0 if ci is None else ci.n,
                        "G": 0 if ci is None else ci.G,
                        "low_cluster": True if ci is None else ci.low_cluster,
                        "tag_label": PROXY_LABEL,
                    }
                )
    result = pl.DataFrame(rows, infer_schema_length=None)
    if quote_coverage is not None:
        coverage_summary = _quote_coverage_summary(quote_coverage)
        result = result.with_columns(
            *[
                pl.lit(value).alias(name)
                for name, value in coverage_summary.items()
            ]
        )
    return result


def _funding_conditioning(events: pl.DataFrame, funding: pl.DataFrame) -> pl.DataFrame:
    by_market: dict[str, tuple[list[datetime], list[float]]] = {}
    for market in TARGETS:
        frame = funding.filter(pl.col("market") == market)
        by_market[market] = (
            frame["time_exchange"].to_list(),
            [float(value) for value in frame["hourly_rate"]],
        )
    rows = []
    for event in events.iter_rows(named=True):
        times, rates = by_market[event["market"]]
        left = bisect_left(times, event["start_time"] - timedelta(hours=24))
        right = bisect_left(times, event["start_time"])
        mean_rate = None if right <= left else sum(rates[left:right]) / (right - left)
        apr = None if mean_rate is None else mean_rate * 24.0 * 365.0
        if apr is None:
            bucket = "unavailable"
        elif apr < 0:
            bucket = "negative"
        elif apr < 0.25:
            bucket = "0%-25%"
        elif apr < 1.0:
            bucket = "25%-100%"
        else:
            bucket = ">=100%"
        krx = label_krx(event["start_time"].replace(tzinfo=UTC))
        rows.append(
            {
                "event_id": event["event_id"],
                "market": event["market"],
                "start_time": event["start_time"],
                "funding_trailing_24h_mean_apr": apr,
                "funding_state": bucket,
                "funding_observations": right - left,
                "krx_state": "live" if krx == "RTH" else "frozen",
                "krx_session_label": krx,
                "tag_label": PROXY_LABEL,
            }
        )
    return pl.DataFrame(rows)


def _oracle_conditioning(events: pl.DataFrame) -> pl.DataFrame:
    inventory: dict[str, list[Path]] = {market: [] for market in TARGETS}
    for path in sorted((DATA / "T-HLORACLEPRICES").rglob("*.csv.gz")):
        name = path.name
        for market in TARGETS:
            if f"S-{market}.csv.gz" in name:
                inventory[market].append(path)
    timelines: dict[str, tuple[list[datetime], list[str]]] = {}
    for market, paths in inventory.items():
        parts = [
            scan_oracle_prices(path, columns=ORACLE_COLUMNS)
            .filter(pl.col("coin_id") == market)
            .select("time_exchange", "update_class")
            .collect(engine="streaming")
            for path in paths
        ]
        frame = pl.concat(parts, how="vertical_relaxed").sort("time_exchange") if parts else pl.DataFrame()
        timelines[market] = (
            [] if frame.is_empty() else frame["time_exchange"].to_list(),
            [] if frame.is_empty() else frame["update_class"].to_list(),
        )
    rows = []
    for event in events.iter_rows(named=True):
        times, classes = timelines[event["market"]]
        left = bisect_left(times, event["start_time"] - timedelta(minutes=30))
        right = bisect_right(times, event["end_time"] + timedelta(minutes=30))
        sample = classes[left:right]
        deployer = sum(value == "Deployer" for value in sample)
        fallback = sum(value == "Fallback" for value in sample)
        total = deployer + fallback
        rows.append(
            {
                "event_id": event["event_id"],
                "oracle_deployer_updates": deployer,
                "oracle_fallback_updates": fallback,
                "oracle_fallback_frequency": None if total == 0 else fallback / total,
                "oracle_regime": (
                    "unavailable"
                    if total == 0
                    else ("fallback-present" if fallback else "deployer-only")
                ),
                "oracle_observations": total,
            }
        )
    return pl.DataFrame(rows, infer_schema_length=None)


def _conditioning_outputs(events: pl.DataFrame, anatomy: pl.DataFrame, funding: pl.DataFrame) -> None:
    conditioning = _funding_conditioning(events, funding).join(
        _oracle_conditioning(events), on="event_id", how="left"
    )
    conditioning.write_parquet(CONDITIONING_PATH)
    joined = conditioning.join(
        anatomy.select(
            "event_id",
            "overshoot_bps",
            "reversion_half_life_seconds",
            "reversion_censored",
            "zero_overshoot",
            "depth_levels_consumed",
            "depth_size_consumed",
        ),
        on="event_id",
        how="left",
    )
    funding_summary = joined.group_by("market", "funding_state").agg(
        pl.len().alias("event_n"),
        pl.col("overshoot_bps").mean().alias("mean_overshoot_bps"),
        pl.col("reversion_half_life_seconds").mean().alias("mean_reversion_half_life_seconds"),
        pl.col("reversion_censored").sum().alias("censored_count"),
        pl.col("zero_overshoot").sum().alias("zero_overshoot_count"),
        pl.col("depth_levels_consumed").mean().alias("mean_depth_levels_consumed"),
        pl.lit(PROXY_LABEL).first().alias("tag_label"),
    )
    funding_summary.write_parquet(FUNDING_SUMMARY_PATH)
    oracle_summary = joined.group_by("market", "krx_state", "oracle_regime").agg(
        pl.len().alias("event_n"),
        pl.col("oracle_fallback_frequency").mean().alias("mean_fallback_frequency"),
        pl.col("overshoot_bps").mean().alias("mean_overshoot_bps"),
        pl.col("reversion_half_life_seconds").mean().alias("mean_reversion_half_life_seconds"),
        pl.col("reversion_censored").sum().alias("censored_count"),
        pl.col("zero_overshoot").sum().alias("zero_overshoot_count"),
        pl.lit(PROXY_LABEL).first().alias("tag_label"),
    )
    oracle_summary.write_parquet(ORACLE_SUMMARY_PATH)

    # The supplied T5 artifacts contain funding but no historical OI series.
    # A null, explicitly unavailable census prevents any post-event/current OI
    # from being silently backfilled into historical conditioning.
    daily = events.select(
        "market", pl.col("start_time").dt.date().alias("date")
    ).unique().sort(["market", "date"])
    daily.with_columns(
        pl.lit(None, dtype=pl.Float64).alias("open_interest"),
        pl.lit(False).alias("available"),
        pl.lit("historical OI absent from supplied T5 inputs").alias("source"),
        pl.lit(PROXY_LABEL).alias("tag_label"),
    ).write_parquet(OI_PATH)


def run_analysis() -> dict[str, object]:
    plan = json.loads(PLAN_PATH.read_text())
    if plan.get("stop"):
        raise RuntimeError(f"analysis plan is stopped: {plan}")
    pairs = _selected_pairs(plan)
    selected_pair_ids = {pair.pair_id for pair in pairs}
    all_events = _event_rows_with_ids(pl.read_parquet(EVENTS_PATH))
    merged = merge_event_windows(pl.read_parquet(EVENTS_PATH))
    event_ids = {
        event_id
        for item in merged
        if item.pair_id in selected_pair_ids
        for event_id in item.event_ids
    }
    events = all_events.filter(pl.col("event_id").is_in(event_ids))
    if DEPTH_SAMPLES_PATH.exists():
        depth = pl.read_parquet(DEPTH_SAMPLES_PATH)
        depth_errors = ["loaded checkpoint from prior bounded depth pass"]
    else:
        depth, depth_errors = _build_depth_samples(events)
        if depth.is_empty():
            raise RuntimeError("no depth samples were produced")
        depth.write_parquet(DEPTH_SAMPLES_PATH, compression="zstd")
    quote_inventory = _inventory("QUOTES")
    trade_inventory = _inventory("TRADES")
    anatomy, anatomy_errors = _event_anatomy(events, depth, quote_inventory)
    if anatomy.is_empty():
        raise RuntimeError("no event anatomy rows were produced")
    anatomy_metric_columns = [
        column
        for column in anatomy.columns
        if column not in events.columns and column != "event_id"
    ]
    covered = anatomy.select("event_id").unique().with_columns(
        pl.lit(True).alias("anatomy_covered")
    )
    computed_anatomy_rows = anatomy.height
    anatomy = (
        events.join(
            anatomy.select("event_id", *anatomy_metric_columns),
            on="event_id",
            how="left",
        )
        .join(covered, on="event_id", how="left")
        .with_columns(
            pl.col("anatomy_covered").fill_null(False),
            pl.when(pl.col("anatomy_covered").fill_null(False))
            .then(pl.lit("computed"))
            .otherwise(pl.lit("unavailable executable-quote/depth coverage"))
            .alias("anatomy_coverage"),
        )
    )
    anatomy.write_parquet(ANATOMY_PATH, compression="zstd")
    funding = _funding_frame()
    fills, markout_errors, quote_coverage = _run_markouts(
        pairs, quote_inventory, trade_inventory, funding
    )
    if fills.is_empty():
        raise RuntimeError("no markout fills were produced")
    fills.write_parquet(FILLS_PATH, compression="zstd")
    quote_coverage.write_parquet(QUOTE_COVERAGE_PATH, compression="zstd")
    quote_coverage_metadata = _quote_coverage_summary(quote_coverage)
    summary = _markout_summary(fills, quote_coverage)
    summary.write_parquet(MARKOUT_PATH)
    _conditioning_outputs(events, anatomy, funding)
    reversion_metadata = {
        "mean_reversion_half_life_seconds": anatomy[
            "reversion_half_life_seconds"
        ].mean(),
        "censored_count": int(anatomy["reversion_censored"].sum() or 0),
        "zero_overshoot_count": int(anatomy["zero_overshoot"].sum() or 0),
    }
    metadata = {
        "tag_label": PROXY_LABEL,
        "events_selected": events.height,
        "anatomy_rows": anatomy.height,
        "anatomy_computed_rows": computed_anatomy_rows,
        "fill_rows": fills.height,
        "markout_summary_rows": summary.height,
        "depth_errors": depth_errors,
        "anatomy_errors": anatomy_errors,
        "markout_errors": markout_errors,
        "quote_coverage": quote_coverage_metadata,
        "reversion": reversion_metadata,
        "funding_buckets_apr": ["negative", "0%-25%", "25%-100%", ">=100%"],
        "oi_limitation": "historical OI absent from supplied T5 inputs; null census emitted",
        "memory_cap": "prlimit --as=6442450944",
    }
    ANALYSIS_META_PATH.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(json.dumps(metadata, sort_keys=True), flush=True)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["plan", "download", "analysis", "all"], required=True)
    args = parser.parse_args()
    if args.phase in {"plan", "all"}:
        plan_pull()
    if args.phase in {"download", "all"}:
        download_pull()
    if args.phase in {"analysis", "all"}:
        run_analysis()


if __name__ == "__main__":
    main()
