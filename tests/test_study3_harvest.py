import json
from datetime import datetime

import httpx
import polars as pl

from charybdis.hl_rest import HyperliquidInfo
from charybdis import study3_harvest
from charybdis.study3_harvest import detect_hourly_gaps, reconcile_expected_rows


HOUR_MS = 3_600_000


def _series(time_column: str, times: list[int]) -> pl.DataFrame:
    return pl.DataFrame({time_column: times}, schema={time_column: pl.Int64})


def _coverage(
    *,
    funding: list[int],
    candles_1h: list[int],
    candles_1d: list[int] | None = None,
    harvest_end_ms: int = 10 * HOUR_MS,
) -> dict[str, object]:
    return study3_harvest.audit_market_coverage(
        funding=_series("time_ms", funding),
        candles_1h=_series("open_time_ms", candles_1h),
        candles_1d=_series("open_time_ms", candles_1d or []),
        harvest_end_ms=harvest_end_ms,
        truncation_tolerance_ms=2 * HOUR_MS,
    )


def test_gap_detector_reports_exact_missing_hours() -> None:
    times = [0, HOUR_MS, 4 * HOUR_MS, 5 * HOUR_MS]

    assert detect_hourly_gaps(times) == [
        {
            "start_ms": 2 * HOUR_MS,
            "end_ms": 3 * HOUR_MS,
            "n_missing": 2,
        }
    ]


def test_gap_detector_reports_no_gaps_for_contiguous_hours() -> None:
    times = [10 * HOUR_MS + offset * HOUR_MS for offset in range(5)]

    assert detect_hourly_gaps(times) == []


def test_reconcile_expected_rows_uses_market_inception() -> None:
    inception_ms = 100 * HOUR_MS
    last_ms = inception_ms + 5 * HOUR_MS

    result = reconcile_expected_rows(
        actual_rows=5,
        inception_ms=inception_ms,
        last_ms=last_ms,
        step_ms=HOUR_MS,
        tolerance_rows=1,
    )

    assert result == {
        "inception_utc": datetime(1970, 1, 5, 4, 0).isoformat(),
        "last_utc": datetime(1970, 1, 5, 9, 0).isoformat(),
        "actual_rows": 5,
        "expected_rows": 6,
        "difference_rows": -1,
        "within_tolerance": True,
    }


def test_audit_classifies_candles_ending_before_funding_as_truncated() -> None:
    result = _coverage(
        funding=list(range(5 * HOUR_MS, 11 * HOUR_MS, HOUR_MS)),
        candles_1h=list(range(5 * HOUR_MS, 8 * HOUR_MS, HOUR_MS)),
    )

    assert result["coverage_status"] == "candle_truncated"
    assert result["candle_funding_shortfall_hours"] == 3.0
    assert result["gap_audit_clean"] is False


def test_audit_classifies_zero_row_market_as_no_data() -> None:
    result = _coverage(funding=[], candles_1h=[])

    assert result["coverage_status"] == "no_data"
    assert result["gap_audit_clean"] is False
    assert result["funding_last_utc"] is None
    assert result["candle_1h_last_utc"] is None


def test_audit_classifies_stale_funding_as_truncated() -> None:
    result = _coverage(
        funding=list(range(3 * HOUR_MS, 7 * HOUR_MS, HOUR_MS)),
        candles_1h=list(range(3 * HOUR_MS, 7 * HOUR_MS, HOUR_MS)),
    )

    assert result["coverage_status"] == "funding_truncated"
    assert result["gap_audit_clean"] is False


def test_audit_classifies_fully_covered_market_as_complete() -> None:
    result = _coverage(
        funding=list(range(5 * HOUR_MS, 11 * HOUR_MS, HOUR_MS)),
        candles_1h=list(range(5 * HOUR_MS, 11 * HOUR_MS, HOUR_MS)),
        candles_1d=[0],
    )

    assert result["coverage_status"] == "complete"
    assert result["gap_audit_clean"] is True
    assert result["funding_row_count"] == 6
    assert result["funding_last_utc"] == datetime(1970, 1, 1, 10).isoformat()
    assert result["candle_1h_last_utc"] == datetime(1970, 1, 1, 10).isoformat()
    assert result["candle_1d_last_utc"] == datetime(1970, 1, 1).isoformat()


def test_audit_records_when_inception_is_the_sanity_floor() -> None:
    floor = study3_harvest.EARLIEST_SANE_MS

    result = _coverage(
        funding=[floor, floor + HOUR_MS],
        candles_1h=[floor, floor + HOUR_MS],
        harvest_end_ms=floor + HOUR_MS,
    )

    assert result["inception_floored"] is True


def test_reaudit_existing_rebuilds_manifest_without_harvesting(tmp_path) -> None:
    output_dir = tmp_path / "reports"
    output_dir.mkdir()
    report_path = tmp_path / "report.md"
    end_ms = 10 * HOUR_MS
    manifest = {
        "schema_version": 1,
        "harvest_end_ms": end_ms,
        "universe": {
            "hip3_total": 2,
            "per_dex_counts": {"test": 2},
            "missing_expected_markets": [],
        },
        "markets": {"test:FULL": {"dex": "test"}, "test:EMPTY": {"dex": "test"}},
        "totals": {
            "markets": 2,
            "funding_rows": 2,
            "candles_1h_rows": 2,
            "candles_1d_rows": 1,
            "snapshot_rows": 2,
        },
        "gap_summary": {"clean_markets": 2, "markets_with_gaps": 0, "examples": []},
        "run": {
            "rest_calls": 0,
            "cache_hits": 0,
            "wall_clock_seconds": 1.0,
            "log_path": "unused.log",
        },
    }
    (output_dir / "study3_harvest_manifest.json").write_text(json.dumps(manifest))
    pl.DataFrame(
        {"market": ["test:FULL", "test:FULL"], "time_ms": [9 * HOUR_MS, end_ms]}
    ).write_parquet(output_dir / "study3_funding_all.parquet")
    pl.DataFrame(
        {"market": ["test:FULL", "test:FULL"], "open_time_ms": [9 * HOUR_MS, end_ms]}
    ).write_parquet(output_dir / "study3_candles_1h.parquet")
    pl.DataFrame(
        {"market": ["test:FULL"], "open_time_ms": [0]}
    ).write_parquet(output_dir / "study3_candles_1d.parquet")

    result = study3_harvest.reaudit_existing(output_dir, report_path)

    assert result["coverage_summary"]["status_counts"] == {
        "no_data": 1,
        "candle_truncated": 0,
        "funding_truncated": 0,
        "complete": 1,
    }
    assert result["markets"]["test:EMPTY"]["gap_audit_clean"] is False
    assert "Interior contiguity" in report_path.read_text()


def test_main_dex_meta_and_asset_context_request_omits_dex(tmp_path) -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200,
            json=[{"universe": [{"name": "BTC"}]}, [{"markPx": "1"}]],
        )

    client = HyperliquidInfo(
        cache_dir=tmp_path,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        requests_per_second=2,
    )

    metadata, contexts = client.meta_and_asset_ctxs(dex=None)

    assert bodies == [{"type": "metaAndAssetCtxs"}]
    assert metadata == {"universe": [{"name": "BTC"}]}
    assert contexts == [{"markPx": "1"}]
