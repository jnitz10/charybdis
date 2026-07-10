"""Build Study 3 S-A census artifacts entirely from T1 on-disk outputs."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import polars as pl

from charybdis.study3_census import (
    APR_FACTOR,
    LIQUIDITY_FLOOR_USD,
    add_mean_apr_bootstrap_cis,
    build_capacity_map,
    build_census,
    build_frozen_universe,
)


REPORTS = Path("data/reports")
FUNDING_PATH = REPORTS / "study3_funding_all.parquet"
SNAPSHOTS_PATH = REPORTS / "study3_snapshots.parquet"
MANIFEST_PATH = REPORTS / "study3_harvest_manifest.json"
CENSUS_PATH = REPORTS / "study3_sa_census.parquet"
UNIVERSE_PATH = REPORTS / "study3_universe.parquet"
CAPACITY_PATH = REPORTS / "study3_carry_capacity.parquet"
REPORT_PATH = Path("docs/reports/study3_funding_census_2026-07-10.md")


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text())
    coverage = {
        market: details["coverage_status"]
        for market, details in manifest["markets"].items()
    }
    coverage_counts = Counter(coverage.values())

    # Projection is deliberate: premium, dex, and time_ms are not needed here.
    funding = (
        pl.scan_parquet(FUNDING_PATH)
        .select("market", "time_exchange", "funding_rate")
        .collect(engine="streaming")
    )
    snapshots = (
        pl.scan_parquet(SNAPSHOTS_PATH)
        .select("market", "openInterest", "oraclePx", "dayNtlVlm")
        .collect(engine="streaming")
    )

    census = build_census(funding, coverage)
    census = add_mean_apr_bootstrap_cis(census, funding)
    carry_count = census.filter(pl.col("carry_relevant")).height
    census = (
        census.with_columns(
            pl.lit(APR_FACTOR).alias("apr_hours_per_year"),
            pl.lit("2026-07-10").alias("analysis_date"),
            pl.lit(0.5).alias("carry_rank_corr_threshold"),
            pl.lit(24.0).alias("carry_half_life_threshold_hours"),
            pl.lit(1.5).alias("regime_gap_break_hours"),
            pl.lit(0.25).alias("regime_25_threshold_apr"),
            pl.lit(1.00).alias("regime_100_threshold_apr"),
            pl.lit(3.00).alias("regime_300_threshold_apr"),
            pl.lit(0.95).alias("bootstrap_confidence_level"),
            pl.lit(coverage_counts.get("complete", 0)).alias(
                "coverage_complete_count"
            ),
            pl.lit(coverage_counts.get("candle_truncated", 0)).alias(
                "coverage_candle_truncated_count"
            ),
            pl.lit(coverage_counts.get("funding_truncated", 0)).alias(
                "coverage_funding_truncated_count"
            ),
            pl.lit(coverage_counts.get("no_data", 0)).alias(
                "coverage_no_data_count"
            ),
            pl.lit(carry_count).alias("carry_relevant_count"),
        )
        .sort("mean_apr", descending=True)
        .with_row_index("mean_apr_rank", offset=1)
    )
    capacity = build_capacity_map(census, snapshots)
    universe = build_frozen_universe(census, snapshots)

    census.write_parquet(CENSUS_PATH, compression="zstd")
    universe.write_parquet(UNIVERSE_PATH, compression="zstd")
    capacity.write_parquet(CAPACITY_PATH, compression="zstd")
    REPORT_PATH.write_text(_render_report(census, capacity, universe))


def _render_report(
    census: pl.DataFrame, capacity: pl.DataFrame, universe: pl.DataFrame
) -> str:
    first = census.row(0, named=True)
    lines = [
        "# Study 3 S-A: funding census and persistence",
        "",
        f"Run date: {first['analysis_date']}. This report contains measurements, intervals, and pre-registered boolean flags only.",
        "",
        "## Coverage and method",
        "",
        (
            f"The T1 manifest records {first['coverage_complete_count']} complete, "
            f"{first['coverage_candle_truncated_count']} candle-truncated, "
            f"{first['coverage_funding_truncated_count']} funding-truncated, and "
            f"{first['coverage_no_data_count']} no-data markets. Funding-based S-A "
            "includes complete and candle-truncated markets and excludes only no-data "
            "markets. Settlement timestamps are used as-is without shifting."
        ),
        "",
        (
            f"APR annualizes the hourly settlement rate by {first['apr_hours_per_year']:.0f}. "
            f"Mean-APR intervals use {first['bootstrap_resamples']} market × UTC-six-hour "
            f"cluster resamples, seed {first['bootstrap_seed']}, and minimum "
            f"G={first['bootstrap_min_clusters']} at confidence level "
            f"{first['bootstrap_confidence_level']:.2f}."
        ),
        "",
        "Sources: `study3_sa_census.parquet` columns `analysis_date`, `coverage_*_count`, `apr_hours_per_year`, `bootstrap_resamples`, `bootstrap_seed`, `bootstrap_min_clusters`, and `bootstrap_confidence_level`.",
        "",
        "## Ranked census",
        "",
        "APR values are decimal annual rates. A blank interval means fewer than the minimum clusters.",
        "",
        "| Rank | Market | Coverage | n | Mean APR (95% CI) | Median APR | Positive hours | AC(1) | AC(24) | Half-life h | Weekly rank rho | Carry-relevant |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for row in census.iter_rows(named=True):
        interval = (
            ""
            if row["mean_apr_ci_low"] is None
            else f"{row['mean_apr']:.4f} [{row['mean_apr_ci_low']:.4f}, {row['mean_apr_ci_high']:.4f}]"
        )
        if not interval:
            interval = f"{row['mean_apr']:.4f} [insufficient clusters]"
        lines.append(
            f"| {row['mean_apr_rank']} | {row['market']} | {row['coverage_status']} | "
            f"{row['n_funding_hours']} | {interval} | {row['median_apr']:.4f} | "
            f"{row['pct_positive_hours']:.4f} | {_fmt(row['ac1'])} | "
            f"{_fmt(row['ac24'])} | {_fmt(row['shock_half_life_hours'])} | "
            f"{_fmt(row['week_over_week_rank_corr'])} | "
            f"{'true' if row['carry_relevant'] else 'false'} |"
        )
    lines.extend(
        [
            "",
            "Source: direct cells in `study3_sa_census.parquet` columns `mean_apr_rank`, `market`, `coverage_status`, `n_funding_hours`, `mean_apr`, `mean_apr_ci_low`, `mean_apr_ci_high`, `median_apr`, `pct_positive_hours`, `ac1`, `ac24`, `shock_half_life_hours`, `week_over_week_rank_corr`, and `carry_relevant`.",
            "",
            "## Funding-regime durations",
            "",
            (
                f"Runs are strictly above APR thresholds {first['regime_25_threshold_apr']:.2f}, "
                f"{first['regime_100_threshold_apr']:.2f}, and "
                f"{first['regime_300_threshold_apr']:.2f}. Cells show count / mean hours / median hours."
            ),
            "",
            "| Market | >25% APR | >100% APR | >300% APR |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in census.iter_rows(named=True):
        lines.append(
            f"| {row['market']} | {_regime_cell(row, '25')} | "
            f"{_regime_cell(row, '100')} | {_regime_cell(row, '300')} |"
        )
    lines.extend(
        [
            "",
            "Source: direct cells in `study3_sa_census.parquet` columns `regime_*_count`, `regime_*_mean_hours`, `regime_*_median_hours`, and `regime_*_threshold_apr`.",
            "",
            "## Persistence classification",
            "",
            (
                f"The pre-registered bar is rank rho ≥ {first['carry_rank_corr_threshold']:.1f} "
                f"and shock half-life ≥ {first['carry_half_life_threshold_hours']:.0f} hours. "
                f"The artifact marks {first['carry_relevant_count']} markets carry-relevant."
            ),
            "",
            "Per-market rank persistence is the lag-1 Spearman correlation of that market's Monday-start weekly cross-sectional rank series. The census also stores the mean and median adjacent-week cross-sectional Spearman correlations across shared markets.",
            "",
            "Source: `study3_sa_census.parquet` columns `carry_rank_corr_threshold`, `carry_half_life_threshold_hours`, `carry_relevant_count`, `weekly_rank_observations`, `week_over_week_rank_corr`, `cross_section_week_pair_corr_mean`, and `cross_section_week_pair_corr_median`.",
            "",
            "## Carry-capacity highlights",
            "",
            "Open interest is reported both in raw base units and as oracle-price-valued notional. The products below multiply mean APR by OI notional and by trailing day notional volume; they are scale maps, not executable capacity estimates.",
            "",
            "| Market | Mean APR | OI base | OI notional USD | Day volume USD | APR × OI notional USD | APR × day volume USD |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in capacity.filter(
        pl.col("market").str.contains(":", literal=True)
    ).head(10).iter_rows(named=True):
        lines.append(
            f"| {row['market']} | {row['mean_apr']:.4f} | "
            f"{_fmt(row['open_interest_base'], 2)} | "
            f"{_fmt(row['open_interest_notional_usd'], 2)} | "
            f"{_fmt(row['day_ntl_vlm_usd'], 2)} | "
            f"{_fmt(row['mean_apr_x_open_interest_notional_usd'], 2)} | "
            f"{_fmt(row['mean_apr_x_day_ntl_vlm_usd'], 2)} |"
        )
    lines.extend(
        [
            "",
            "Source: direct cells in `study3_carry_capacity.parquet` columns shown in the table.",
            "",
            "## Frozen T3 universe",
            "",
            (
                f"The HIP-3-only universe applies the strict day-volume floor of "
                f"USD {universe['liquidity_floor_usd'][0]:,.0f}; main-dex BTC/ETH/SOL "
                "reference rows remain in the census but are not T3 universe rows."
            ),
            "",
            "Source: `study3_universe.parquet` columns `market`, `coverage_status`, `passes_liquidity_floor`, `liquidity_floor_usd`, `carry_relevant`, `mean_apr`, `open_interest_base`, `open_interest_notional_usd`, and `day_ntl_vlm_usd`.",
            "",
            "## Biases and assumptions",
            "",
            "- Snapshot OI and day volume are current cross-sectional size proxies joined by exact market key; they are not historical executable depth.",
            "- OI notional uses the snapshot oracle price. APR × size products can be negative and do not model slippage, borrow, fees, or liquidation constraints.",
            "- AR(1) uses OLS with an intercept on adjacent hourly settlements. Half-life is null unless the fitted coefficient is strictly between zero and one.",
            f"- Regime runs use strict APR thresholds and break on an inter-settlement gap longer than {first['regime_gap_break_hours']:.1f} hours. No funding row is shifted backward to the premium-formation hour.",
            "- Weekly ranks use partial inception/final weeks when present; differing market inception dates reduce rank-series observations for newer markets.",
            "- Candle truncation does not remove funding observations. No-data markets have no census statistic; funding-truncated status is retained explicitly when present.",
            "",
        ]
    )
    return "\n".join(lines)


def _fmt(value: object, digits: int = 4) -> str:
    return "" if value is None else f"{float(value):.{digits}f}"


def _regime_cell(row: dict[str, object], label: str) -> str:
    return (
        f"{row[f'regime_{label}_count']} / "
        f"{_fmt(row[f'regime_{label}_mean_hours'], 2)} / "
        f"{_fmt(row[f'regime_{label}_median_hours'], 2)}"
    )


if __name__ == "__main__":
    main()
