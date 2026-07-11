"""Generate Study-3 S-F funding-to-proxy-flow artifacts from local parquet only."""

from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path

import polars as pl
import pyarrow.parquet as pq

from charybdis.study3_funding_forced_flow import (
    BUCKET_ORDER,
    add_sign_size_deciles,
    build_exposure_panel,
    causal_conditioning_buckets,
    hazard_table,
    market_clustered_rate_ratio,
    summarize_bucket_rates,
    summarize_event_rates,
    wallet_bridge,
)


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "data/reports"
FUNDING_PATH = REPORTS / "study3_funding_all.parquet"
UNIVERSE_PATH = REPORTS / "study3_universe.parquet"
EVENTS_PATH = REPORTS / "forced_flow_events_proxy.parquet"
RATE_PATH = REPORTS / "study3_sf_event_rates.parquet"
HAZARD_PATH = REPORTS / "study3_sf_hazard.parquet"
DOC_PATH = ROOT / "docs/reports/study3_funding_forced_flow_2026-07-10.md"
MARKETS = ("SKHX", "SMSN")
FUNDING_MARKETS = ("xyz:SKHX", "xyz:SMSN")
BUCKET_DEFINITIONS = {
    "negative": "APR < 0%",
    "0_to_25pct": "0% <= APR < 25%",
    "25_to_100pct": "25% <= APR < 100%",
    "ge_100pct": "APR >= 100%",
}


def _projected_parquet(path: Path, columns: list[str], *, filters=None) -> pl.DataFrame:
    """Read only selected parquet columns, with optional PyArrow pushdown filters."""

    return pl.from_arrow(pq.read_table(path, columns=columns, filters=filters))


def load_inputs() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    universe = _projected_parquet(
        UNIVERSE_PATH,
        ["market", "coverage_status", "passes_liquidity_floor"],
        filters=[("market", "in", list(FUNDING_MARKETS))],
    )
    missing_universe = sorted(set(FUNDING_MARKETS) - set(universe["market"].to_list()))
    if missing_universe:
        raise ValueError(f"Study-3 universe missing proxy markets: {missing_universe}")
    funding = _projected_parquet(
        FUNDING_PATH,
        ["market", "time_exchange", "funding_rate"],
        filters=[("market", "in", list(FUNDING_MARKETS))],
    ).with_columns(pl.col("market").str.split(":").list.last())
    events = _projected_parquet(
        EVENTS_PATH,
        ["market", "start_time", "direction", "wallets", "trigger_source", "tag_label"],
        filters=[("market", "in", list(MARKETS))],
    )
    if events.height != 2_573:
        raise ValueError(f"expected 2,573 proxy events, found {events.height:,}")
    if set(events["trigger_source"].unique().to_list()) != {"proxy"}:
        raise ValueError("event artifact contains a non-proxy trigger source")
    if set(events["tag_label"].unique().to_list()) != {"proxy-tagged"}:
        raise ValueError("event artifact contains a non-proxy tag label")
    return universe, funding, events


def _fmt(value: object, digits: int = 6) -> str:
    if value is None:
        return "NA"
    return f"{float(value):.{digits}f}"


def _markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return "\n".join(lines)


def _rate_rows(rates: pl.DataFrame) -> list[list[object]]:
    return [
        [
            row["funding_bucket"],
            row["bucket_definition"],
            row["event_count"],
            _fmt(row["exposure_hours"], 3),
            _fmt(row["event_rate_per_market_hour"]),
            f"[{_fmt(row['ci_low'])}, {_fmt(row['ci_high'])}]",
            row["clusters"],
        ]
        for row in rates.iter_rows(named=True)
    ]


def ff_conclusion(ratios: pl.DataFrame) -> str:
    """Apply the pre-specified F-F verdict to per-market, not pooled, CIs."""

    per_market = ratios.filter(pl.col("scope") != "ALL")
    all_market_cis_include_one = per_market.height > 0 and all(
        row["ci_low"] is not None
        and row["ci_high"] is not None
        and row["ci_low"] <= 1.0 <= row["ci_high"]
        for row in per_market.iter_rows(named=True)
    )
    pooled = ratios.filter(pl.col("scope") == "ALL")
    pooled_below_one = (
        pooled.height == 1 and float(pooled.row(0, named=True)["rate_ratio"]) < 1.0
    )
    if all_market_cis_include_one:
        direction = (
            " The pooled point estimate is below 1, opposite the "
            "‘high funding → more events’ hypothesis."
            if pooled_below_one
            else ""
        )
        return (
            "The per-market CIs both include 1: there is no timing effect; "
            "funding's role is market-selection only."
            + direction
        )
    return "Per-market intervals do not all include 1; the planned timing test is unresolved."


def write_report(
    primary_rates: pl.DataFrame,
    secondary_rates: pl.DataFrame,
    ratios: pl.DataFrame,
    market_clustered_ratio: dict[str, object],
    hazard: pl.DataFrame,
    wallet_summary: dict[str, object],
    *,
    window_start,
    window_end,
) -> None:
    ratio_rows = []
    for row in ratios.iter_rows(named=True):
        excludes = bool(
            row["ci_low"] is not None
            and row["ci_high"] is not None
            and (row["ci_low"] > 1.0 or row["ci_high"] < 1.0)
        )
        ratio_rows.append(
            [
                row["scope"],
                _fmt(row["rate_ratio"], 4),
                f"[{_fmt(row['ci_low'], 4)}, {_fmt(row['ci_high'], 4)}]",
                str(excludes).lower(),
                row["clusters"],
            ]
        )
    selection_fact = ff_conclusion(ratios)
    market_cluster_ci = (
        "insufficient evidence (low_cluster)"
        if market_clustered_ratio["low_cluster"]
        else f"[{_fmt(market_clustered_ratio['ci_low'], 4)}, "
        f"{_fmt(market_clustered_ratio['ci_high'], 4)}]"
    )
    hazard_rows = [
        [
            row["scope"],
            _fmt(row["hazard_horizon_hours"], 0),
            row["funding_bucket"],
            row["conditioning_observations"],
            row["event_within_horizon_count"],
            _fmt(row["probability_event_within_horizon"], 4),
            "saturated / uninformative" if row["coverage_saturated"] else "informative",
        ]
        for row in hazard.iter_rows(named=True)
    ]
    secondary_display = secondary_rates.sort("funding_bucket")
    text = f"""# Study 3 S-F: funding → forced-flow linkage

Run date: 2026-07-10.

> **COVERAGE CAVEAT — This is only a two-market SKHX/SMSN linkage study over the proxy window 2026-05-27 to 2026-07-08. All 2,573 events are proxy-tagged repeated-taker burst events from the Study-2 fallback, not observations from a real liquidation feed. The results are not venue-wide and do not measure confirmed liquidations (Study-2 gap G2).**

The measured exposure interval is `{window_start.isoformat(sep=' ')}` through `{window_end.isoformat(sep=' ')}` (the first through last proxy-event timestamps, with the final timestamp included). Funding APR is the settled hourly rate multiplied by 24 × 365. A funding state starts only when its settlement is known and is held until the next settlement. Exposure is split at market × UTC-six-hour boundaries.

## Event rate by funding bucket

The denominator is explicit: `event rate = proxy-event count / market-hours of funding-bucket exposure`, pooled across SKHX and SMSN. Confidence intervals are percentile cluster-bootstrap intervals with 2,000 resamples of whole market × UTC-six-hour blocks, using `markout.py`'s shared bootstrap machinery.

{_markdown_table(['funding bucket', 'definition', 'proxy events', 'exposure market-hours', 'events / market-hour', '95% cluster-bootstrap CI', 'clusters'], _rate_rows(primary_rates))}

## High-versus-low rate ratios

`high` is APR >= 100%; `low` is APR < 0%. Each ratio is `(high events / high exposure hours) / (low events / low exposure hours)`.

{_markdown_table(['scope', 'high/low rate ratio', '95% cluster-bootstrap CI', 'CI excludes 1', 'clusters'], ratio_rows)}

Serial-correlation diagnostic (whole market as the cluster):

{_markdown_table(['scope', 'high/low rate ratio', 'market-clustered CI/status', 'market clusters'], [['ALL', _fmt(market_clustered_ratio['rate_ratio'], 4), market_cluster_ci, market_clustered_ratio['clusters']]])}

## F-F status

{_markdown_table(['scope', 'high/low rate ratio', '95% CI', 'CI excludes 1', 'clusters'], ratio_rows)}

{selection_fact}

## Leading-indicator hazard table

Conditioning observations are hourly funding settlements with a complete forward outcome window. The bucket at time `t` uses only the latest same-market settlement at or before `t`; the binary outcome checks forward for a same-market proxy event in `(t, t+horizon]`. No later funding value is used for conditioning.

The 24-hour hazard is coverage-limited and uninformative for these two near-continuous markets: its bucket probabilities are saturated near a base rate of 1. The 2-hour horizon is reported as the discriminating view.

{_markdown_table(['scope', 'horizon hours', 'funding bucket at t', 'conditioning observations', 'event within horizon', 'P(event within horizon)', 'coverage diagnostic'], hazard_rows)}

## 1.6 Wallet bridge

Minimum forward window: **{_fmt(wallet_summary['min_forward_window_hours'], 0)} hours**. Right-censored high-APR BUY wallets: **{wallet_summary['right_censored_high_regime_long_wallets']:,}**.

{_markdown_table(['cohort/control', 'eligible wallets', 'later reappearance fraction', 'high-APR BUY minus control'], [
    ['high-APR BUY cohort', wallet_summary['high_regime_long_accumulator_wallets'], _fmt(wallet_summary['bridge_fraction'], 4), '0.0000'],
    ['low-APR BUY control (<0% or 0-25%)', wallet_summary['low_apr_buy_control_wallets'], _fmt(wallet_summary['low_apr_buy_control_fraction'], 4), _fmt(wallet_summary['bridge_minus_low_apr_buy'], 4)],
    ['>=100% APR SELL control', wallet_summary['high_apr_sell_control_wallets'], _fmt(wallet_summary['high_apr_sell_control_fraction'], 4), _fmt(wallet_summary['bridge_minus_high_apr_sell'], 4)],
    ['full proxy-wallet population', wallet_summary['proxy_population_control_wallets'], _fmt(wallet_summary['proxy_population_control_fraction'], 4), _fmt(wallet_summary['bridge_minus_proxy_population'], 4)],
])}

{"The wallet bridge shows NO funding-specific linkage." if not wallet_summary['funding_specific_linkage'] else ""}

## Secondary sign × size-decile cut

Absolute-APR size deciles are weighted by market-hours; the sign is retained separately. These are secondary descriptive rates, not the F-F ratio definition.

{_markdown_table(['sign × absolute-APR decile', 'definition', 'proxy events', 'exposure market-hours', 'events / market-hour', '95% cluster-bootstrap CI', 'clusters'], _rate_rows(secondary_display))}

## Reproducibility and scope

Inputs were projected with PyArrow to only the columns used from `study3_funding_all.parquet`, `study3_universe.parquet`, and `forced_flow_events_proxy.parquet`. This run made no network calls and touched no order, wallet, or key paths. Spend remained $116.92; task spend was $0.
"""
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(text)


def main() -> None:
    _, funding, events = load_inputs()
    window_start = events["start_time"].min()
    last_event = events["start_time"].max()
    window_end = last_event + timedelta(microseconds=1)
    panel = build_exposure_panel(
        funding,
        events.select("market", "start_time"),
        window_start=window_start,
        window_end=window_end,
    )
    primary_rates, ratios = summarize_event_rates(panel, n_resamples=2_000, seed=30_701)
    market_ratio = market_clustered_rate_ratio(
        panel, n_resamples=2_000, seed=30_703
    )
    primary_rates = primary_rates.with_columns(
        pl.lit("apr_bucket").alias("analysis_cut"),
        pl.col("funding_bucket").replace_strict(BUCKET_DEFINITIONS).alias("bucket_definition"),
        pl.col("funding_bucket").replace_strict(
            {bucket: index for index, bucket in enumerate(BUCKET_ORDER)}
        ).alias("bucket_order"),
    ).sort("bucket_order")

    secondary_panel = add_sign_size_deciles(panel).with_columns(
        pl.col("sign_size_decile").alias("funding_bucket")
    )
    secondary_rates = summarize_bucket_rates(
        secondary_panel, n_resamples=2_000, seed=30_702
    ).with_columns(
        pl.lit("sign_x_abs_apr_decile").alias("analysis_cut"),
        pl.lit("exposure-weighted absolute-APR decile, sign retained").alias(
            "bucket_definition"
        ),
        pl.col("funding_bucket").str.extract(r"D(\d+)$", 1).cast(pl.Int64).alias("bucket_order"),
    )
    event_rates = pl.concat([primary_rates, secondary_rates], how="diagonal_relaxed").select(
        "analysis_cut",
        "bucket_order",
        "funding_bucket",
        "bucket_definition",
        "event_count",
        "exposure_hours",
        "event_rate_per_market_hour",
        "ci_low",
        "ci_high",
        "clusters",
        "low_cluster",
    )
    event_rates.write_parquet(RATE_PATH)

    hazard_parts = []
    for horizon_hours in (24, 2):
        latest_conditioning = window_end - timedelta(hours=horizon_hours)
        conditioning_times = funding.filter(
            (pl.col("time_exchange") >= window_start)
            & (pl.col("time_exchange") <= latest_conditioning)
        ).select(pl.col("market"), pl.col("time_exchange").alias("conditioning_time"))
        conditioning = causal_conditioning_buckets(funding, conditioning_times)
        for scope, selected in [
            ("ALL", conditioning),
            *[
                (market, conditioning.filter(pl.col("market") == market))
                for market in MARKETS
            ],
        ]:
            hazard_parts.append(
                hazard_table(
                    selected,
                    events.select("market", "start_time"),
                    horizon=timedelta(hours=horizon_hours),
                ).with_columns(
                    pl.lit(scope).alias("scope"),
                    pl.col("funding_bucket").replace_strict(
                        {bucket: index for index, bucket in enumerate(BUCKET_ORDER)}
                    ).alias("bucket_order"),
                )
            )
    hazard = pl.concat(hazard_parts).select(
        "scope",
        "bucket_order",
        "funding_bucket",
        "conditioning_observations",
        "event_within_horizon_count",
        "probability_event_within_horizon",
        "hazard_horizon_hours",
        "coverage_saturated",
    ).sort(["scope", "hazard_horizon_hours", "bucket_order"], descending=[False, True, False])
    hazard.write_parquet(HAZARD_PATH)

    event_times = events.select(
        "market", pl.col("start_time").alias("conditioning_time")
    )
    event_buckets = causal_conditioning_buckets(funding, event_times)
    bridge_events = events.select("market", "start_time", "direction", "wallets").with_columns(
        event_buckets["funding_bucket"]
    )
    _, wallet_summary = wallet_bridge(bridge_events)
    write_report(
        primary_rates,
        secondary_rates,
        ratios,
        market_ratio,
        hazard,
        wallet_summary,
        window_start=window_start,
        window_end=last_event,
    )
    print(
        json.dumps(
            {
                "event_rates": str(RATE_PATH),
                "hazard": str(HAZARD_PATH),
                "report": str(DOC_PATH),
                "events": events.height,
                "exposure_hours": panel["exposure_hours"].sum(),
                "wallet_bridge": wallet_summary,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
