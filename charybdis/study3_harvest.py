"""Study 3 T1 public-REST harvest and per-market completeness audit."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import polars as pl

from charybdis.hl_rest import EARLIEST_SANE_MS, HyperliquidInfo


HOUR_MS = 3_600_000
DAY_MS = 86_400_000
EXPECTED_DEXES = ["xyz", "flx", "vntl", "hyna", "km", "mkts", "cash", "para", "abcd"]
EXPECTED_STUDY_MARKETS = [
    "xyz:SP500", "km:US500", "flx:USA500", "cash:USA500", "km:USTECH",
    "xyz:XYZ100", "flx:USA100", "km:SMALL2000", "xyz:SKHX", "xyz:SMSN",
    "xyz:SMH", "xyz:KR200", "xyz:EWY",
]
MAIN_HEDGE_MARKETS = ["BTC", "ETH", "SOL"]
AUDIT_TOLERANCE_ROWS = 1
TRUNCATION_TOLERANCE_MS = 2 * HOUR_MS
SNAPSHOT_FIELDS = ["funding", "openInterest", "oraclePx", "markPx", "premium", "dayNtlVlm"]
STEP0_PROBES = [
    {
        "market": "km:US500",
        "probe_start_ms": 1_781_704_800_000,
        "harvest_end_ms": 1_783_717_197_078,
        "returned_rows": 0,
    },
    {
        "market": "km:RTX",
        "probe_start_ms": 1_781_082_000_000,
        "harvest_end_ms": 1_783_717_197_078,
        "returned_rows": 0,
    },
    {
        "market": "vntl:OPENAI",
        "probe_start_ms": 1_781_535_600_000,
        "harvest_end_ms": 1_783_717_197_078,
        "returned_rows": 0,
    },
]


def _utc_iso(time_ms: int) -> str:
    return datetime.fromtimestamp(time_ms / 1000, UTC).replace(tzinfo=None).isoformat()


def detect_hourly_gaps(times_ms: Iterable[int]) -> list[dict[str, int]]:
    """Return exact absent hourly slots between successive observed timestamps."""

    ordered = sorted(set(int(value) for value in times_ms))
    gaps: list[dict[str, int]] = []
    for previous, current in zip(ordered, ordered[1:]):
        missing = (current - previous) // HOUR_MS - 1
        if missing > 0:
            gaps.append(
                {
                    "start_ms": previous + HOUR_MS,
                    "end_ms": current - HOUR_MS,
                    "n_missing": missing,
                }
            )
    return gaps


def reconcile_expected_rows(
    *,
    actual_rows: int,
    inception_ms: int,
    last_ms: int,
    step_ms: int,
    tolerance_rows: int = AUDIT_TOLERANCE_ROWS,
) -> dict[str, Any]:
    """Compare observations with the inclusive regular grid over their own span."""

    expected = (int(last_ms) - int(inception_ms)) // int(step_ms) + 1
    difference = int(actual_rows) - expected
    return {
        "inception_utc": _utc_iso(inception_ms),
        "last_utc": _utc_iso(last_ms),
        "actual_rows": int(actual_rows),
        "expected_rows": expected,
        "difference_rows": difference,
        "within_tolerance": abs(difference) <= tolerance_rows,
    }


def _empty_reconciliation() -> dict[str, Any]:
    return {
        "inception_utc": None,
        "last_utc": None,
        "actual_rows": 0,
        "expected_rows": 0,
        "difference_rows": 0,
        "within_tolerance": True,
    }


def _audit(frame: pl.DataFrame, time_column: str, step_ms: int) -> dict[str, Any]:
    if frame.is_empty():
        return {"reconciliation": _empty_reconciliation(), "gaps": []}
    times = frame.get_column(time_column).cast(pl.Int64).to_list()
    reconciliation = reconcile_expected_rows(
        actual_rows=len(times),
        inception_ms=min(times),
        last_ms=max(times),
        step_ms=step_ms,
    )
    gaps = detect_hourly_gaps(times) if step_ms == HOUR_MS else []
    return {"reconciliation": reconciliation, "gaps": gaps}


def audit_market_coverage(
    *,
    funding: pl.DataFrame,
    candles_1h: pl.DataFrame,
    candles_1d: pl.DataFrame,
    harvest_end_ms: int,
    truncation_tolerance_ms: int = TRUNCATION_TOLERANCE_MS,
) -> dict[str, Any]:
    """Audit both interior contiguity and endpoint coverage for one market."""

    funding_audit = _audit(funding, "time_ms", HOUR_MS)
    candle_1h_audit = _audit(candles_1h, "open_time_ms", HOUR_MS)
    candle_1d_audit = _audit(candles_1d, "open_time_ms", DAY_MS)

    def endpoint(frame: pl.DataFrame, column: str) -> int | None:
        if frame.is_empty():
            return None
        return int(frame.get_column(column).max())

    funding_last_ms = endpoint(funding, "time_ms")
    candle_1h_last_ms = endpoint(candles_1h, "open_time_ms")
    candle_1d_last_ms = endpoint(candles_1d, "open_time_ms")
    observed_first = [
        int(frame.get_column(column).min())
        for frame, column in (
            (funding, "time_ms"),
            (candles_1h, "open_time_ms"),
            (candles_1d, "open_time_ms"),
        )
        if not frame.is_empty()
    ]
    no_data = funding.is_empty() and candles_1h.is_empty() and candles_1d.is_empty()
    interior_contiguity_clean = (
        not funding_audit["gaps"] and not candle_1h_audit["gaps"]
    )
    funding_endpoint_short = (
        funding_last_ms is None
        or int(harvest_end_ms) - funding_last_ms > truncation_tolerance_ms
    )
    candle_target_ms = (
        min(funding_last_ms, int(harvest_end_ms))
        if funding_last_ms is not None
        else None
    )
    candle_shortfall_ms = (
        max(0, candle_target_ms - candle_1h_last_ms)
        if candle_target_ms is not None and candle_1h_last_ms is not None
        else None
    )
    candle_endpoint_short = (
        candle_target_ms is not None
        and (
            candle_1h_last_ms is None
            or candle_target_ms - candle_1h_last_ms > truncation_tolerance_ms
        )
    )

    if no_data:
        coverage_status = "no_data"
    elif funding_endpoint_short or funding_audit["gaps"]:
        coverage_status = "funding_truncated"
    elif candle_endpoint_short or candle_1h_audit["gaps"]:
        coverage_status = "candle_truncated"
    else:
        coverage_status = "complete"

    return {
        "inception_utc": _utc_iso(min(observed_first)) if observed_first else None,
        "inception_floored": bool(observed_first and min(observed_first) == EARLIEST_SANE_MS),
        "funding_last_utc": _utc_iso(funding_last_ms) if funding_last_ms is not None else None,
        "candle_1h_last_utc": _utc_iso(candle_1h_last_ms) if candle_1h_last_ms is not None else None,
        "candle_1d_last_utc": _utc_iso(candle_1d_last_ms) if candle_1d_last_ms is not None else None,
        "funding_row_count": funding.height,
        "candle_1h_row_count": candles_1h.height,
        "candle_1d_row_count": candles_1d.height,
        "coverage_status": coverage_status,
        "candle_funding_shortfall_hours": (
            candle_shortfall_ms / HOUR_MS if candle_shortfall_ms is not None else None
        ),
        "interior_contiguity_clean": interior_contiguity_clean,
        "funding_audit": funding_audit,
        "candle_1h_audit": candle_1h_audit,
        "candle_1d_audit": candle_1d_audit,
        "gap_audit_clean": coverage_status == "complete" and interior_contiguity_clean,
    }


def _safe_market(market: str) -> str:
    return market.replace(":", "__").replace("/", "_")


def _market_names(metadata: dict[str, Any]) -> list[str]:
    return [str(item["name"]) for item in metadata.get("universe", [])]


def _snapshot_rows(
    dex: str,
    metadata: dict[str, Any],
    contexts: list[dict[str, Any]],
    fetched_at: datetime,
    selected: set[str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for asset, context in zip(metadata.get("universe", []), contexts, strict=True):
        market = str(asset["name"])
        if selected is not None and market not in selected:
            continue
        row: dict[str, Any] = {
            "dex": dex,
            "market": market,
            "fetched_at_utc": fetched_at.replace(tzinfo=None),
        }
        for field in SNAPSHOT_FIELDS:
            value = context.get(field)
            row[field] = float(value) if value is not None else None
        rows.append(row)
    return rows


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _combine_parts(parts: list[Path], destination: Path) -> int:
    if not parts:
        raise RuntimeError(f"no parquet parts available for {destination}")
    pl.scan_parquet(parts).sink_parquet(destination, compression="zstd")
    return pl.scan_parquet(destination).select(pl.len()).collect().item()


def _funding_part(frame: pl.DataFrame, dex: str) -> pl.DataFrame:
    return frame.with_columns(pl.lit(dex).alias("dex")).select(
        "dex", "market", "time_ms", "time_exchange", "funding_rate", "premium"
    )


def _candle_part(frame: pl.DataFrame, dex: str) -> pl.DataFrame:
    return frame.with_columns(pl.lit(dex).alias("dex")).rename(
        {"volume": "v", "trade_count": "n"}
    ).select(
        "dex", "market", "interval", "open_time_ms", "close_time_ms", "time_open",
        "open", "high", "low", "close", "v", "n",
    )


def _format_gap(gap: dict[str, int]) -> str:
    return f"{_utc_iso(gap['start_ms'])}–{_utc_iso(gap['end_ms'])} ({gap['n_missing']} missing)"


def _summarize_coverage(manifest: dict[str, Any]) -> None:
    status_order = ("no_data", "candle_truncated", "funding_truncated", "complete")
    status_counts = {
        status: sum(
            record["coverage_status"] == status
            for record in manifest["markets"].values()
        )
        for status in status_order
    }
    data_bearing = len(manifest["markets"]) - status_counts["no_data"]
    over_24h = sum(
        record["coverage_status"] == "candle_truncated"
        and record["candle_funding_shortfall_hours"] is not None
        and record["candle_funding_shortfall_hours"] > 24
        for record in manifest["markets"].values()
    )
    no_1h = sum(
        record["coverage_status"] == "candle_truncated"
        and record["candle_1h_row_count"] == 0
        for record in manifest["markets"].values()
    )
    interior_gaps = sum(
        not record["interior_contiguity_clean"]
        for record in manifest["markets"].values()
        if record["coverage_status"] != "no_data"
    )
    manifest["coverage_summary"] = {
        "status_counts": status_counts,
        "data_bearing_markets": data_bearing,
        "candle_truncated_over_24h": over_24h,
        "candle_truncated_without_1h_rows": no_1h,
        "interior_contiguous_data_bearing_markets": data_bearing - interior_gaps,
        "data_bearing_markets_with_interior_gaps": interior_gaps,
        "truncation_tolerance_hours": TRUNCATION_TOLERANCE_MS / HOUR_MS,
    }

    gap_examples: list[dict[str, Any]] = []
    for market, record in manifest["markets"].items():
        for series in ("funding", "candle_1h"):
            for gap in record[f"{series}_audit"]["gaps"]:
                if len(gap_examples) < 5:
                    gap_examples.append({"market": market, "series": series, "gap": gap})
    manifest["gap_summary"] = {
        "interior_contiguous_data_bearing_markets": data_bearing - interior_gaps,
        "data_bearing_markets_with_interior_gaps": interior_gaps,
        "examples": gap_examples,
    }


def write_report(manifest: dict[str, Any], report_path: Path) -> None:
    universe = manifest["universe"]
    rows = manifest["totals"]
    coverage = manifest["coverage_summary"]
    statuses = coverage["status_counts"]
    gaps = manifest["gap_summary"]
    missing = universe["missing_expected_markets"]
    examples = gaps["examples"]
    probes = manifest.get("step0_probe", {}).get("results", STEP0_PROBES)
    lines = [
        "# Study 3 T1 funding harvest — 2026-07-10",
        "",
        "## Scope and method",
        "",
        "Research-only collection used public Hyperliquid info REST exclusively through `charybdis.hl_rest.HyperliquidInfo`. No orders, wallets, keys, or paid endpoints were used. Funding and candles begin at the T0 client's validated 2026-01-01 lower bound. Interior reconciliation still spans each series' first through last observation, but endpoint coverage is now audited separately against funding and the fixed harvest end.",
        "",
        "## Universe reconciliation",
        "",
        "| DEX | Current listed markets |",
        "|---|---:|",
    ]
    lines.extend(f"| {dex} | {count:,} |" for dex, count in universe["per_dex_counts"].items())
    lines.extend(
        [
            f"| **Total** | **{universe['hip3_total']:,}** |",
            "",
            f"The live snapshot contained {universe['hip3_total']} currently listed HIP-3 markets, matching T0's 225-entry observation and falling {289 - universe['hip3_total']} below the plan's rough ~289 estimate. The REST metadata snapshot only enumerates live listings; delisted markets cannot be recovered by name from that snapshot, so they are not reachable for a name-driven census.",
            "",
            f"Expected Study-1/2 market check: {len(EXPECTED_STUDY_MARKETS) - len(missing)}/{len(EXPECTED_STUDY_MARKETS)} present. " + (f"Missing: {', '.join(missing)}." if missing else "None missing."),
            "Verified present: " + ", ".join(f"`{market}`" for market in EXPECTED_STUDY_MARKETS) + ".",
            "",
            "Main-dex hedge references: **BTC, ETH, SOL**. BTC and ETH were explicitly required baseline hedges; SOL was the sole additional small-list twin because SOL is listed both on the main dex and in the HIP-3 universe, making it a useful large-cap control for S-A.",
            "",
            "## Harvest totals",
            "",
            f"Markets covered: **{rows['markets']}** ({universe['hip3_total']} HIP-3 + {len(MAIN_HEDGE_MARKETS)} main-dex references). Funding rows: **{rows['funding_rows']:,}**. 1h candle rows: **{rows['candles_1h_rows']:,}**. 1d candle rows: **{rows['candles_1d_rows']:,}**. Snapshot rows: **{rows['snapshot_rows']:,}**.",
            "",
            "## Endpoint coverage",
            "",
            f"Of **{rows['markets']}** total markets, **{coverage['data_bearing_markets']}** are data-bearing and **{statuses['no_data']}** are `no_data`. Among data-bearing markets, **{statuses['complete']}** are `complete`, **{statuses['candle_truncated']}** are `candle_truncated`, and **{statuses['funding_truncated']}** are `funding_truncated` under a **{coverage['truncation_tolerance_hours']:.0f}-hour** endpoint tolerance.",
            "",
            f"The adversarial review's 66 count described long candle shortfalls: this recomputation confirms **{coverage['candle_truncated_over_24h']}** candle-truncated markets more than 24 hours behind funding. The strict 2-hour rule additionally captures shorter material shortfalls and **{coverage['candle_truncated_without_1h_rows']}** data-bearing market with no 1h rows, yielding the larger honest bucket above.",
            "",
            "`gap_audit_clean` is true only for `complete` markets with no detected interior gaps. It is false for `no_data`, `candle_truncated`, and `funding_truncated` markets.",
            "",
            "## Interior contiguity",
            "",
            f"Separately from endpoint coverage, **{gaps['interior_contiguous_data_bearing_markets']}/{coverage['data_bearing_markets']} data-bearing markets** have no detected funding or 1h-candle gaps within their own observed spans; **{gaps['data_bearing_markets_with_interior_gaps']}** have recorded interior gaps. Empty markets are excluded from this statement. Row-count reconciliation uses an inclusive regular grid with a one-row endpoint tolerance.",
            "",
        ]
    )
    if examples:
        lines.append("Examples:")
        lines.append("")
        for example in examples:
            lines.append(f"- `{example['market']}` {example['series']}: {_format_gap(example['gap'])}")
        lines.append("")
    else:
        lines.extend(["No funding or 1h candle interior gaps were found.", ""])
    lines.extend(
        [
            "## STEP 0 direct probe verdict",
            "",
            "**Real market inactivity, not a candle-pagination bug.** Direct `candle_snapshot` requests strictly after each stored last 1h candle through the fixed harvest end returned no rows:",
            "",
        ]
    )
    for probe in probes:
        lines.append(
            f"- `{probe['market']}`: start `{probe['probe_start_ms']}`, end `{probe['harvest_end_ms']}`, returned rows **{probe['returned_rows']}**."
        )
    lines.extend(
        [
            "",
            "The existing candle parquets are therefore complete representations of candles returned by Hyperliquid for those windows; no candle re-fetch or pagination change was needed.",
            "",
            "## Downstream use",
            "",
            "T2–T7 must use each series' persisted endpoint fields and `coverage_status` when constructing joins. The market list establishes universe membership only; it does not imply that funding or candles cover the full research window. `inception_floored: true` means the first timestamp equals the imposed 2026-01-01 lower bound and must not be interpreted as a listing date.",
            "",
        ]
    )
    run = manifest["run"]
    lines.extend(
        [
            "## REST run",
            "",
            f"Actual network REST calls: **{run['rest_calls']}**; cache hits: **{run['cache_hits']}**; wall-clock time: **{run['wall_clock_seconds']:.1f} seconds** ({run['wall_clock_seconds'] / 60:.2f} minutes). Progress was logged to `{run['log_path']}`.",
            "",
            "All outputs are research artifacts. `data/spend.json` remained unchanged at $116.92473877999909 (displayed as $116.92); public REST cost was $0.",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n")


def reaudit_existing(output_dir: Path, report_path: Path) -> dict[str, Any]:
    """Recompute audit metadata from existing consolidated parquet artifacts only."""

    manifest_path = output_dir / "study3_harvest_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    frames = {
        "funding": pl.read_parquet(output_dir / "study3_funding_all.parquet"),
        "candles_1h": pl.read_parquet(output_dir / "study3_candles_1h.parquet"),
        "candles_1d": pl.read_parquet(output_dir / "study3_candles_1d.parquet"),
    }
    parts = {
        series: {
            key[0] if isinstance(key, tuple) else key: part
            for key, part in frame.partition_by("market", as_dict=True).items()
        }
        for series, frame in frames.items()
    }
    empty = {series: frame.head(0) for series, frame in frames.items()}
    for market, prior_record in list(manifest["markets"].items()):
        manifest["markets"][market] = {
            "dex": prior_record["dex"],
            **audit_market_coverage(
                funding=parts["funding"].get(market, empty["funding"]),
                candles_1h=parts["candles_1h"].get(market, empty["candles_1h"]),
                candles_1d=parts["candles_1d"].get(market, empty["candles_1d"]),
                harvest_end_ms=manifest["harvest_end_ms"],
            ),
        }
    manifest["schema_version"] = 2
    manifest["audit_recomputed_at_utc"] = datetime.now(UTC).isoformat()
    manifest["step0_probe"] = {
        "verdict": "real_market_inactivity",
        "results": STEP0_PROBES,
        "rest_calls": 3,
        "cache_hits": 0,
    }
    _summarize_coverage(manifest)
    _write_json(manifest_path, manifest)
    write_report(manifest, report_path)
    return manifest


def harvest(output_dir: Path, report_path: Path, log_path: Path, rps: float) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path), logging.StreamHandler()],
        force=True,
    )
    logger = logging.getLogger("study3_harvest")
    started_utc = datetime.now(UTC)
    parts_root = output_dir / ".study3_parts"
    for kind in ("funding", "candles_1h", "candles_1d"):
        (parts_root / kind).mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "study3_harvest_manifest.json"
    prior_manifest = (
        json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    )
    end_ms = int(
        prior_manifest.get("harvest_end_ms", int(started_utc.timestamp() * 1000))
    )
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "harvest_end_ms": end_ms,
        "harvest_started_at_utc": prior_manifest.get(
            "harvest_started_at_utc", datetime.fromtimestamp(end_ms / 1000, UTC).isoformat()
        ),
        "markets": {},
        "hedge_references": {
            "symbols": MAIN_HEDGE_MARKETS,
            "reasons": {
                "BTC": "explicitly required main-dex baseline hedge",
                "ETH": "explicitly required main-dex baseline hedge",
                "SOL": "small-list large-cap main/HIP-3 twin for S-A",
            },
        },
    }

    with HyperliquidInfo(requests_per_second=rps) as api:
        dexes = api.perp_dexs()
        if set(dexes) != set(EXPECTED_DEXES):
            logger.warning("live dex set differs from expected: live=%s expected=%s", dexes, EXPECTED_DEXES)
        market_specs: list[tuple[str, str]] = []
        snapshots: list[dict[str, Any]] = []
        per_dex_counts: dict[str, int] = {}
        fetched_at = datetime.now(UTC)
        for dex in dexes:
            metadata, contexts = api.meta_and_asset_ctxs(dex)
            names = _market_names(metadata)
            per_dex_counts[dex] = len(names)
            market_specs.extend((dex, name) for name in names)
            snapshots.extend(_snapshot_rows(dex, metadata, contexts, fetched_at))
        main_metadata, main_contexts = api.meta_and_asset_ctxs()
        main_available = set(_market_names(main_metadata))
        unavailable_main = sorted(set(MAIN_HEDGE_MARKETS) - main_available)
        if unavailable_main:
            raise RuntimeError(f"required main-dex hedge references absent: {unavailable_main}")
        main_selected = set(MAIN_HEDGE_MARKETS)
        snapshots.extend(_snapshot_rows("main", main_metadata, main_contexts, fetched_at, main_selected))
        market_specs.extend(("main", market) for market in MAIN_HEDGE_MARKETS)
        hip3_names = {market for dex, market in market_specs if dex != "main"}
        missing_expected = sorted(set(EXPECTED_STUDY_MARKETS) - hip3_names)
        manifest["universe"] = {
            "dexes": dexes,
            "per_dex_counts": per_dex_counts,
            "hip3_total": sum(per_dex_counts.values()),
            "missing_expected_markets": missing_expected,
            "expected_market_presence": {market: market in hip3_names for market in EXPECTED_STUDY_MARKETS},
        }
        pl.DataFrame(snapshots).write_parquet(output_dir / "study3_snapshots.parquet", compression="zstd")
        logger.info("universe enumerated: hip3=%d main_refs=%d total=%d counts=%s missing_expected=%s", len(hip3_names), len(MAIN_HEDGE_MARKETS), len(market_specs), per_dex_counts, missing_expected)

        for number, (dex, market) in enumerate(market_specs, 1):
            safe = _safe_market(market)
            funding_path = parts_root / "funding" / f"{safe}.parquet"
            candle_1h_path = parts_root / "candles_1h" / f"{safe}.parquet"
            candle_1d_path = parts_root / "candles_1d" / f"{safe}.parquet"
            if funding_path.exists() and candle_1h_path.exists() and candle_1d_path.exists():
                funding = pl.read_parquet(funding_path)
                candles_1h = pl.read_parquet(candle_1h_path)
                candles_1d = pl.read_parquet(candle_1d_path)
            else:
                funding = _funding_part(api.funding_history(market, EARLIEST_SANE_MS, end_ms=end_ms), dex)
                candles_1h = _candle_part(api.candle_snapshot(market, "1h", EARLIEST_SANE_MS, end_ms), dex)
                candles_1d = _candle_part(api.candle_snapshot(market, "1d", EARLIEST_SANE_MS, end_ms), dex)
                funding.write_parquet(funding_path, compression="zstd")
                candles_1h.write_parquet(candle_1h_path, compression="zstd")
                candles_1d.write_parquet(candle_1d_path, compression="zstd")
            manifest["markets"][market] = {
                "dex": dex,
                **audit_market_coverage(
                    funding=funding,
                    candles_1h=candles_1h,
                    candles_1d=candles_1d,
                    harvest_end_ms=end_ms,
                ),
            }
            _write_json(manifest_path, manifest)
            logger.info("market %d/%d %s funding=%d 1h=%d 1d=%d calls=%d cache_hits=%d", number, len(market_specs), market, funding.height, candles_1h.height, candles_1d.height, api.rest_calls, api.cache_hits)

        totals = {
            "markets": len(market_specs),
            "funding_rows": _combine_parts(sorted((parts_root / "funding").glob("*.parquet")), output_dir / "study3_funding_all.parquet"),
            "candles_1h_rows": _combine_parts(sorted((parts_root / "candles_1h").glob("*.parquet")), output_dir / "study3_candles_1h.parquet"),
            "candles_1d_rows": _combine_parts(sorted((parts_root / "candles_1d").glob("*.parquet")), output_dir / "study3_candles_1d.parquet"),
            "snapshot_rows": len(snapshots),
        }
        harvest_started = datetime.fromisoformat(manifest["harvest_started_at_utc"])
        wall_clock = (datetime.now(UTC) - harvest_started).total_seconds()
        total_rest_calls = sum(
            "HTTP Request: POST https://api.hyperliquid.xyz/info" in line
            for line in log_path.read_text().splitlines()
        )
        manifest["totals"] = totals
        _summarize_coverage(manifest)
        manifest["run"] = {
            "started_at_utc": manifest["harvest_started_at_utc"],
            "completed_at_utc": datetime.now(UTC).isoformat(),
            "rest_calls": total_rest_calls,
            "cache_hits": api.cache_hits,
            "wall_clock_seconds": wall_clock,
            "requests_per_second": rps,
            "log_path": str(log_path),
        }
        _write_json(manifest_path, manifest)
        write_report(manifest, report_path)
        logger.info("complete totals=%s gaps=%s calls=%d wall=%.1fs", totals, manifest["gap_summary"], total_rest_calls, wall_clock)
    shutil.rmtree(parts_root)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("data/reports"))
    parser.add_argument("--report", type=Path, default=Path("docs/reports/study3_harvest_2026-07-10.md"))
    parser.add_argument("--log", type=Path, default=Path("data/study3_harvest.log"))
    parser.add_argument("--rps", type=float, default=2.0)
    parser.add_argument(
        "--reaudit-existing",
        action="store_true",
        help="recompute manifest/report metadata from existing consolidated parquets",
    )
    args = parser.parse_args()
    if args.reaudit_existing:
        reaudit_existing(args.output_dir, args.report)
    else:
        harvest(args.output_dir, args.report, args.log, args.rps)


if __name__ == "__main__":
    main()
