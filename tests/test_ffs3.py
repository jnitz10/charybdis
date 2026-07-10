from io import StringIO
from pathlib import Path

from charybdis.ffs3 import (
    FlatFilesS3Client,
    GB,
    ObjectInfo,
    SpendMeter,
    build_manifest,
    execute_manifest,
)


def test_spend_meter_order_book_tiers_reset_per_day(tmp_path: Path) -> None:
    meter = SpendMeter(tmp_path / "spend.json")

    assert meter.record("Order Book", "2026-07-09", 1 * GB) == 8.0
    assert meter.record("Order Book", "2026-07-09", 9 * GB) == 36.0
    assert meter.record("Order Book", "2026-07-09", 10 * GB) == 20.0
    assert meter.running_cost_usd == 64.0

    assert meter.record("Order Book", "2026-07-10", 1 * GB) == 8.0
    assert meter.running_cost_usd == 72.0

    reloaded = SpendMeter(tmp_path / "spend.json")
    assert reloaded.bytes_for("Order Book", "2026-07-09") == 20 * GB
    assert reloaded.bytes_for("Order Book", "2026-07-10") == 1 * GB
    assert reloaded.running_cost_usd == 72.0


def test_spend_meter_two_instances_do_not_lose_updates(tmp_path: Path) -> None:
    spend_path = tmp_path / "spend.json"
    first_meter = SpendMeter(spend_path)
    second_meter = SpendMeter(spend_path)

    first_charge = first_meter.record("Order Book", "2026-07-09", 1 * GB)
    second_charge = second_meter.record("Order Book", "2026-07-09", 1 * GB)

    persisted = SpendMeter(spend_path)
    assert persisted.bytes_for("Order Book", "2026-07-09") == 2 * GB
    assert persisted.running_cost_usd == first_charge + second_charge


def test_manifest_does_not_recost_existing_correct_size_file(tmp_path: Path) -> None:
    key = "T-TRADES/D-2026070900/E-EXISTING.csv.gz"
    destination = tmp_path / "data" / key
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"1234")
    meter = SpendMeter(tmp_path / "spend.json")

    manifest = build_manifest(
        [ObjectInfo(key, 4)],
        meter,
        billing_day="2026-07-09",
        data_root=tmp_path / "data",
    )
    result = execute_manifest(
        _NoDownloadClient(),
        manifest,
        meter,
        data_root=tmp_path / "data",
    )

    assert manifest.files[0].estimated_cost_usd == 0.0
    assert manifest.projected_spend_usd == 0.0
    assert result.skipped == 1


def test_list_with_sizes_paginates_using_explicit_and_fallback_markers() -> None:
    for next_marker, expected_marker in (("opaque-next", "opaque-next"), (None, "a/2.gz")):
        class FakeS3Client:
            def __init__(self) -> None:
                self.requests: list[dict[str, object]] = []

            def list_objects(self, **request: object) -> dict[str, object]:
                self.requests.append(request)
                if len(self.requests) == 1:
                    response: dict[str, object] = {
                        "IsTruncated": True,
                        "Contents": [
                            {"Key": "a/1.gz", "Size": 11},
                            {"Key": "a/2.gz", "Size": 22},
                        ],
                    }
                    if next_marker is not None:
                        response["NextMarker"] = next_marker
                    return response
                return {
                    "IsTruncated": False,
                    "Contents": [{"Key": "a/3.gz", "Size": 33}],
                }

        fake = FakeS3Client()
        client = FlatFilesS3Client(s3_client=fake)

        objects = client.list_with_sizes("a/")

        assert [(item.key, item.size) for item in objects] == [
            ("a/1.gz", 11),
            ("a/2.gz", 22),
            ("a/3.gz", 33),
        ]
        assert fake.requests == [
            {"Bucket": "coinapi", "Prefix": "a/"},
            {"Bucket": "coinapi", "Prefix": "a/", "Marker": expected_marker},
        ]


def test_dry_run_over_ceiling_prints_pause_without_downloading(tmp_path: Path) -> None:
    class NoDownloadClient:
        def download_file(self, key: str, destination: Path) -> None:
            raise AssertionError(f"dry-run downloaded {key} to {destination}")

    meter = SpendMeter(tmp_path / "spend.json")
    meter.record("Order Book", "2026-07-09", 153 * GB // 2)
    manifest = build_manifest(
        [
            ObjectInfo(
                "T-LIMITBOOK_FULL/D-2026070900/E-HYPERLIQUIDL4/"
                "IDDI-1+SC-TEST+S-TEST.csv.gz",
                GB // 2,
            )
        ],
        meter,
        billing_day="2026-07-09",
    )
    output = StringIO()

    result = execute_manifest(
        NoDownloadClient(),
        manifest,
        meter,
        data_root=tmp_path / "data",
        dry_run=True,
        output=output,
    )

    assert result.paused is True
    assert result.downloaded == 0
    assert "projected=$178.00" in output.getvalue()
    assert "PAUSE" in output.getvalue()


class _NoDownloadClient:
    def download_file(self, key: str, destination: Path) -> None:
        raise AssertionError(f"unexpected download of {key} to {destination}")
