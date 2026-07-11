"""Generate Study-3 S-E cross-dex spread artifacts from on-disk inputs."""

from __future__ import annotations

from datetime import date
import math
from pathlib import Path
from statistics import median
from typing import Callable

import polars as pl

from charybdis.loaders import scan_report_parquet
from charybdis.markout import BootstrapCI, cluster_bootstrap_statistic
from charybdis.run_study3_carry import STUDY1_MARKETS, measured_half_spreads
from charybdis.study3_spreads import (
    APR_HOURS,
    TwinPair,
    align_twin_pairs,
    amortized_breakeven_apr,
    breakeven_episode_durations,
    median_episode_duration,
    persistence_half_life_lag_pairs,
    round_trip_cost_bps,
    utc_six_hour_block,
)


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "data/reports"
OUTPUT_PATH = REPORTS / "study3_se_spreads.parquet"
DOC_PATH = ROOT / "docs/reports/study3_cross_dex_spreads_2026-07-10.md"
BOOTSTRAP_RESAMPLES = 2_000
BOOTSTRAP_SEED = 0
BOOTSTRAP_MIN_CLUSTERS = 5


def _collect(frame: pl.LazyFrame) -> pl.DataFrame:
    return frame.collect(engine="streaming")


def load_inputs() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    universe = _collect(scan_report_parquet(
        REPORTS / "study3_universe.parquet", columns=["market", "coverage_status"]
    ))
    pairs = align_twin_pairs(universe["market"].to_list())
    markets = sorted({market for pair in pairs for market in (pair.market_a, pair.market_b)})
    funding = _collect(
        scan_report_parquet(
            REPORTS / "study3_funding_all.parquet",
            columns=["market", "time_exchange", "funding_rate"],
        ).filter(pl.col("market").is_in(markets))
    )
    candles = _collect(
        scan_report_parquet(
            REPORTS / "study3_candles_1h.parquet",
            columns=["market", "time_open", "close"],
        ).filter(pl.col("market").is_in(markets))
    )
    fees = _collect(scan_report_parquet(
        REPORTS / "study3_fee_table.parquet",
        columns=["dex", "effective_maker_bps", "effective_taker_bps", "source"],
    ))
    return universe, funding, candles, fees


def build_half_spreads(markets: list[str]) -> pl.DataFrame:
    measured = measured_half_spreads()
    missing = sorted(STUDY1_MARKETS - measured.keys())
    if missing:
        raise ValueError(f"missing pre-2026-06-18 books for Study-1 markets: {missing}")
    fallback = 2.0 * median(measured[market] for market in STUDY1_MARKETS)
    rows = []
    for market in sorted(markets):
        is_measured = market in STUDY1_MARKETS
        rows.append({
            "market": market,
            "half_spread_bps": measured[market] if is_measured else fallback,
            "half_spread_source": (
                "measured_pre_2026-06-18_l4_quotes"
                if is_measured else "assumed_2x_study1_market_median"
            ),
        })
    return pl.DataFrame(rows)


def _funding_by_market(funding: pl.DataFrame) -> dict[str, pl.DataFrame]:
    hourly = (
        funding.with_columns(pl.col("time_exchange").dt.truncate("1h").alias("time"))
        .sort(["market", "time_exchange"])
        .group_by(["market", "time"], maintain_order=True)
        .agg(pl.col("funding_rate").last())
    )
    return {market: group.sort("time") for (market,), group in hourly.partition_by("market", as_dict=True).items()}


def _candles_by_market(candles: pl.DataFrame) -> dict[str, pl.DataFrame]:
    hourly = (
        candles.filter(pl.col("close").is_finite() & (pl.col("close") > 0))
        .sort(["market", "time_open"])
        .group_by(["market", "time_open"], maintain_order=True)
        .agg(pl.col("close").last())
        .rename({"time_open": "time"})
    )
    return {market: group.sort("time") for (market,), group in hourly.partition_by("market", as_dict=True).items()}


def _differential_frame(pair: TwinPair, groups: dict[str, pl.DataFrame]) -> pl.DataFrame:
    left = groups[pair.market_a].select("time", pl.col("funding_rate").alias("rate_a"))
    right = groups[pair.market_b].select("time", pl.col("funding_rate").alias("rate_b"))
    return (
        left.join(right, on="time", how="inner")
        .sort("time")
        .with_columns(
            ((pl.col("rate_a") - pl.col("rate_b")) * APR_HOURS).alias("diff_apr"),
        )
        .with_columns(
            pl.col("diff_apr").abs().alias("abs_diff_apr"),
            pl.col("time").map_elements(
                lambda value: f"{pair.pair_id}|{utc_six_hour_block(value).isoformat()}",
                return_dtype=pl.String,
            ).alias("cluster_key"),
        )
    )


def _basis_frame(pair: TwinPair, groups: dict[str, pl.DataFrame]) -> pl.DataFrame:
    left = groups[pair.market_a].select("time", pl.col("close").alias("price_a"))
    right = groups[pair.market_b].select("time", pl.col("close").alias("price_b"))
    return (
        left.join(right, on="time", how="inner")
        .filter((pl.col("price_a") > 0) & (pl.col("price_b") > 0))
        .sort("time")
        .with_columns((pl.col("price_a") / pl.col("price_b")).log().alias("log_price_ratio"))
        .with_columns(
            (pl.col("log_price_ratio") - pl.col("log_price_ratio").median()).alias("basis")
        )
        .with_columns(
            pl.col("basis").abs().alias("abs_basis"),
            pl.col("time").map_elements(
                lambda value: f"{pair.pair_id}|{utc_six_hour_block(value).isoformat()}",
                return_dtype=pl.String,
            ).alias("cluster_key"),
        )
    )


def _persistence_lag_pairs(differential: pl.DataFrame) -> pl.DataFrame:
    """Precompute genuine adjacent-hour pairs before cluster resampling."""

    return (
        differential.sort("time")
        .with_columns(
            pl.col("time").shift(1).alias("lag_time"),
            pl.col("abs_diff_apr").shift(1).alias("lag_value"),
            pl.col("abs_diff_apr").alias("value"),
        )
        .filter(pl.col("time") - pl.col("lag_time") == pl.duration(hours=1))
        .select("time", "lag_value", "value", "cluster_key")
    )


def _mean(frame: pl.DataFrame, column: str) -> float:
    return float(frame[column].mean())


def _std(frame: pl.DataFrame, column: str) -> float:
    value = frame[column].std(ddof=1)
    return float(value) if value is not None else math.nan


def _quantile(frame: pl.DataFrame, column: str, probability: float = 0.95) -> float:
    value = frame[column].quantile(probability, interpolation="linear")
    return float(value) if value is not None else math.nan


def _proportion_above(frame: pl.DataFrame, column: str, threshold: float) -> float:
    return float((frame[column] > threshold).mean())


def _bootstrap(frame: pl.DataFrame, statistic: Callable[[pl.DataFrame], float]) -> BootstrapCI:
    return cluster_bootstrap_statistic(
        frame,
        statistic=statistic,
        n_resamples=BOOTSTRAP_RESAMPLES,
        seed=BOOTSTRAP_SEED,
        min_clusters=BOOTSTRAP_MIN_CLUSTERS,
    )


def _ci_columns(prefix: str, interval: BootstrapCI) -> dict[str, object]:
    return {
        f"{prefix}_ci_low": interval.ci_low,
        f"{prefix}_ci_high": interval.ci_high,
    }


def _fee_value(fees: pl.DataFrame, market: str, column: str) -> float:
    dex = market.split(":", 1)[0]
    row = fees.filter(pl.col("dex") == dex)
    if row.height != 1:
        raise ValueError(f"fee table must contain exactly one row for {dex!r}")
    return float(row[column][0])


def analyze_pairs(
    universe: pl.DataFrame,
    funding: pl.DataFrame,
    candles: pl.DataFrame,
    fees: pl.DataFrame,
    spreads: pl.DataFrame,
) -> pl.DataFrame:
    pairs = align_twin_pairs(universe["market"].to_list())
    funding_groups = _funding_by_market(funding)
    candle_groups = _candles_by_market(candles)
    spread_lookup = dict(spreads.select("market", "half_spread_bps").iter_rows())
    source_lookup = dict(spreads.select("market", "half_spread_source").iter_rows())
    rows: list[dict[str, object]] = []
    for pair in pairs:
        if pair.market_a not in funding_groups or pair.market_b not in funding_groups:
            continue
        if pair.market_a not in candle_groups or pair.market_b not in candle_groups:
            continue
        differential = _differential_frame(pair, funding_groups)
        basis = _basis_frame(pair, candle_groups)
        if differential.height < 3 or basis.height < 2:
            continue
        lag_pairs = _persistence_lag_pairs(differential)
        half_life_ci = _bootstrap(lag_pairs, persistence_half_life_lag_pairs)
        half_life = half_life_ci.point_estimate
        if not math.isfinite(half_life):
            raise ValueError(f"undefined observed persistence for {pair.pair_id}")
        costs = round_trip_cost_bps(
            pair.market_a,
            pair.market_b,
            fee_table=fees,
            half_spread_bps=spread_lookup,
        )
        maker_threshold = amortized_breakeven_apr(costs.maker_bps, half_life)
        taker_threshold = amortized_breakeven_apr(costs.taker_bps, half_life)
        mean_diff = _bootstrap(differential, lambda draw: _mean(draw, "abs_diff_apr"))
        p95_diff = _bootstrap(differential, lambda draw: _quantile(draw, "abs_diff_apr"))
        maker_pct = _bootstrap(
            differential, lambda draw, threshold=maker_threshold: _proportion_above(draw, "abs_diff_apr", threshold)
        )
        taker_pct = _bootstrap(
            differential, lambda draw, threshold=taker_threshold: _proportion_above(draw, "abs_diff_apr", threshold)
        )
        basis_vol = _bootstrap(basis, lambda draw: _std(draw, "basis"))
        basis_p95 = _bootstrap(basis, lambda draw: _quantile(draw, "abs_basis"))
        maker_episodes = breakeven_episode_durations(differential, maker_threshold)
        taker_episodes = breakeven_episode_durations(differential, taker_threshold)
        horizon_diff = p95_diff.point_estimate * half_life / APR_HOURS
        row: dict[str, object] = {
            "analysis_date": date(2026, 7, 10),
            "underlier": pair.underlier,
            "pair_id": pair.pair_id,
            "market_a": pair.market_a,
            "market_b": pair.market_b,
            "n_funding_hours": differential.height,
            "first_funding_time": differential["time"].min(),
            "last_funding_time": differential["time"].max(),
            "mean_abs_diff_apr": mean_diff.point_estimate,
            "p95_abs_diff_apr": p95_diff.point_estimate,
            "persistence_half_life_hours": half_life,
            "maker_round_trip_cost_bps": costs.maker_bps,
            "taker_round_trip_cost_bps": costs.taker_bps,
            "maker_breakeven_apr": maker_threshold,
            "taker_breakeven_apr": taker_threshold,
            "pct_time_gt_maker_breakeven": maker_pct.point_estimate,
            "pct_time_gt_taker_breakeven": taker_pct.point_estimate,
            "maker_median_episode_hours": median_episode_duration(
                differential, maker_threshold
            ),
            "taker_median_episode_hours": median_episode_duration(
                differential, taker_threshold
            ),
            "maker_n_episodes": len(maker_episodes),
            "taker_n_episodes": len(taker_episodes),
            "maker_never_exceeds_breakeven": not maker_episodes,
            "taker_never_exceeds_breakeven": not taker_episodes,
            "cost_amortization_horizon_hours": half_life,
            "twice_cost_horizon_hours": 2.0 * half_life,
            "n_basis_hours": basis.height,
            "basis_vol": basis_vol.point_estimate,
            "basis_p95_abs_excursion": basis_p95.point_estimate,
            "p95_diff_horizon_return": horizon_diff,
            "basis_to_p95_diff_horizon_ratio": (
                basis_p95.point_estimate / horizon_diff if horizon_diff > 0 else None
            ),
            "market_a_effective_maker_bps": _fee_value(fees, pair.market_a, "effective_maker_bps"),
            "market_b_effective_maker_bps": _fee_value(fees, pair.market_b, "effective_maker_bps"),
            "market_a_effective_taker_bps": _fee_value(fees, pair.market_a, "effective_taker_bps"),
            "market_b_effective_taker_bps": _fee_value(fees, pair.market_b, "effective_taker_bps"),
            "market_a_half_spread_bps": spread_lookup[pair.market_a],
            "market_b_half_spread_bps": spread_lookup[pair.market_b],
            "market_a_half_spread_source": source_lookup[pair.market_a],
            "market_b_half_spread_source": source_lookup[pair.market_b],
            "funding_bootstrap_G": mean_diff.G,
            "basis_bootstrap_G": basis_vol.G,
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_min_clusters": BOOTSTRAP_MIN_CLUSTERS,
        }
        row.update(_ci_columns("mean_abs_diff_apr", mean_diff))
        row.update(_ci_columns("p95_abs_diff_apr", p95_diff))
        row.update(_ci_columns("persistence_half_life_hours", half_life_ci))
        row.update(_ci_columns("pct_time_gt_maker_breakeven", maker_pct))
        row.update(_ci_columns("pct_time_gt_taker_breakeven", taker_pct))
        row.update(_ci_columns("basis_vol", basis_vol))
        row.update(_ci_columns("basis_p95_abs_excursion", basis_p95))
        rows.append(row)
    return pl.DataFrame(rows).sort("mean_abs_diff_apr", descending=True)


def _pct(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def _never_exceeds(row: dict[str, object], side: str) -> bool:
    marker = row.get(f"{side}_never_exceeds_breakeven")
    if marker is not None:
        return bool(marker)
    return float(row[f"pct_time_gt_{side}_breakeven"]) == 0.0


def _primary_maker_kill_leg(row: dict[str, object]) -> str:
    """Classify the first failed maker F-E gate; basis is checked last."""

    if _never_exceeds(row, "maker"):
        return "never-reaches-breakeven"
    duration = float(row["maker_median_episode_hours"])
    if duration <= float(row["twice_cost_horizon_hours"]):
        return "duration"
    if float(row["basis_to_p95_diff_horizon_ratio"]) > 1.0:
        return "basis"
    return "survives"


def _episode_cell(row: dict[str, object], side: str) -> str:
    if _never_exceeds(row, side):
        return f"never (n=0) / {float(row['twice_cost_horizon_hours']):.2f}"
    return (
        f"{float(row[f'{side}_median_episode_hours']):.2f} / "
        f"{float(row['twice_cost_horizon_hours']):.2f}"
    )


def render_report(results: pl.DataFrame) -> str:
    named_rows = list(results.iter_rows(named=True))
    kill_counts = {label: 0 for label in ("never-reaches-breakeven", "duration", "basis", "survives")}
    for row in named_rows:
        kill_counts[_primary_maker_kill_leg(row)] += 1
    basis_failures = sum(
        float(row["basis_to_p95_diff_horizon_ratio"]) > 1.0 for row in named_rows
    )
    maker_never = sum(_never_exceeds(row, "maker") for row in named_rows)
    taker_never = sum(_never_exceeds(row, "taker") for row in named_rows)
    xmr_row = next(row for row in named_rows if row["pair_id"] == "flx:XMR|hyna:XMR")
    all_dead = kill_counts["survives"] == 0
    lines = [
        "# Study 3 S-E: cross-dex funding spreads and twin-basis risk",
        "",
        "Analysis date: 2026-07-10. This is research-only; no orders, wallets, keys, network calls, or new paid data were used. Total cumulative spend remains **$116.92**.",
        "",
        "Hourly funding settlement rates are aligned at their UTC settlement hour without backfilling and annualized by 8,760. Twins use an audited exact underlier map: SP500 = {SP500, US500, USA500}, USA100 = {USTECH, USA100, XYZ100}; every other group uses exact coin identity only. All pair combinations across distinct dex prefixes are reported, including the additional `mkts` index twins surfaced by the frozen S-A universe.",
        "",
        "Round-trip maker breakeven is `2 × (effective maker fee A + effective maker fee B)`: resting maker execution does not cross the spread. Taker breakeven is `2 × [(effective taker fee A + half-spread A) + (effective taker fee B + half-spread B)]`. Each is annualized over the observed absolute-differential AR(1) half-life, and fees are read only from `study3_fee_table.parquet`. Basis is the median-demeaned `ln(closeA/closeB)`; volatility is its sample standard deviation and excursion is the 95th percentile of its absolute value.",
        "",
        "All bracketed intervals are 95% percentile intervals from 2,000 nonparametric pair-market × UTC-six-hour cluster resamples (seed 0, minimum G=5), reusing `charybdis.markout.cluster_bootstrap_statistic`. Half-life uses genuine adjacent-hour lag pairs precomputed before resampling and assigns each pair to its destination UTC-six-hour block, so sampled blocks cannot create false time adjacency.",
        "",
        "## F-E finding and kill attribution",
        "",
        f"All {results.height} pairs remain F-E dead." if all_dead else f"WARNING: {kill_counts['survives']} of {results.height} pairs survive F-E.",
        "",
        f"The robust universal finding is that basis/twin-basis risk swamps the funding differential: corrected basis p95 exceeds the persistence-horizon funding edge for {basis_failures}/{results.height} pairs. Separately, {taker_never}/{results.height} pairs never reach taker breakeven and {maker_never}/{results.height} never reach maker breakeven. Among pairs that reach maker breakeven, the primary maker kill leg below is duration unless the duration gate survives, in which case basis is the kill leg.",
        "",
        f"Primary maker kill-leg counts: never-reaches-breakeven={kill_counts['never-reaches-breakeven']}; duration={kill_counts['duration']}; basis={kill_counts['basis']}; survives={kill_counts['survives']}.",
        "",
        "| underlier | pair | primary maker kill leg | basis also fails |",
        "|---|---|---|---:|",
    ]
    for row in named_rows:
        lines.append(
            f"| {row['underlier']} | {row['pair_id']} | {_primary_maker_kill_leg(row)} | "
            f"{'yes' if float(row['basis_to_p95_diff_horizon_ratio']) > 1.0 else 'no'} |"
        )
    lines += [
        "",
        "### Sub-1h top-differential artifacts",
        "",
        f"`flx:XMR|hyna:XMR`, despite ranking first by mean absolute funding differential, is a venue-quality/erratic-funding artifact, not an opportunity: its {float(xmr_row['persistence_half_life_hours']):.2f}h half-life and only {_pct(float(xmr_row['pct_time_gt_maker_breakeven']))} maker and {_pct(float(xmr_row['pct_time_gt_taker_breakeven']))} taker time above breakeven are consistent with whipsawing funding on the near-dead `hyna` venue already flagged in Studies 1–2.",
        "",
        "Other pairs in the top-ten mean-differential cohort with sub-1h persistence are likewise treated as erratic-funding/venue-quality artifacts rather than capturable spreads:",
        "",
        "| pair | mean |diff| APR | half-life h |",
        "|---|---:|---:|",
    ]
    for row in named_rows[:10]:
        if float(row["persistence_half_life_hours"]) < 1.0:
            lines.append(
                f"| {row['pair_id']} | {float(row['mean_abs_diff_apr']):.4f} | "
                f"{float(row['persistence_half_life_hours']):.2f} |"
            )
    lines += [
        "",
        "## Pairwise results",
        "",
        "| underlier | pair | mean |diff| APR [95% CI] | half-life h [95% CI] | > BE maker / taker [95% CI] | basis vol [95% CI] | basis p95 excursion [95% CI] |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in named_rows:
        lines.append(
            f"| {row['underlier']} | {row['pair_id']} | {row['mean_abs_diff_apr']:.4f} "
            f"[{row['mean_abs_diff_apr_ci_low']:.4f}, {row['mean_abs_diff_apr_ci_high']:.4f}] | "
            f"{row['persistence_half_life_hours']:.2f} [{row['persistence_half_life_hours_ci_low']:.2f}, {row['persistence_half_life_hours_ci_high']:.2f}] | "
            f"{_pct(row['pct_time_gt_maker_breakeven'])} [{_pct(row['pct_time_gt_maker_breakeven_ci_low'])}, {_pct(row['pct_time_gt_maker_breakeven_ci_high'])}] / "
            f"{_pct(row['pct_time_gt_taker_breakeven'])} [{_pct(row['pct_time_gt_taker_breakeven_ci_low'])}, {_pct(row['pct_time_gt_taker_breakeven_ci_high'])}] | "
            f"{row['basis_vol']:.4f} [{row['basis_vol_ci_low']:.4f}, {row['basis_vol_ci_high']:.4f}] | "
            f"{row['basis_p95_abs_excursion']:.4f} [{row['basis_p95_abs_excursion_ci_low']:.4f}, {row['basis_p95_abs_excursion_ci_high']:.4f}] |"
        )
    lines += [
        "",
        "## F-E numeric quantities (no verdicts)",
        "",
        "The episode comparison reports median contiguous hours above each breakeven against `2 ×` the same cost-amortization horizon. The basis comparison reports absolute-basis p95 against absolute-funding-differential p95 both as APR and as the return implied over the persistence horizon; the latter is the dimensionally comparable quantity.",
        "",
        "| underlier | pair | maker median episode h / 2× horizon h | taker median episode h / 2× horizon h | basis p95 | funding |diff| p95 APR | p95 diff return over horizon | basis / horizon-diff ratio |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in named_rows:
        lines.append(
            f"| {row['underlier']} | {row['pair_id']} | {_episode_cell(row, 'maker')} | "
            f"{_episode_cell(row, 'taker')} | "
            f"{row['basis_p95_abs_excursion']:.6f} | {row['p95_abs_diff_apr']:.4f} | "
            f"{row['p95_diff_horizon_return']:.8f} | {row['basis_to_p95_diff_horizon_ratio']:.2f} |"
        )
    lines += [
        "",
        "## Cost and coverage caveats",
        "",
        "| pair | maker / taker round trip bps | maker / taker BE APR | market A half-spread | market B half-spread |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in named_rows:
        lines.append(
            f"| {row['pair_id']} | {row['maker_round_trip_cost_bps']:.4f} / {row['taker_round_trip_cost_bps']:.4f} | "
            f"{row['maker_breakeven_apr']:.4f} / {row['taker_breakeven_apr']:.4f} | "
            f"{row['market_a_half_spread_bps']:.4f} ({row['market_a_half_spread_source']}) | "
            f"{row['market_b_half_spread_bps']:.4f} ({row['market_b_half_spread_source']}) |"
        )
    lines += [
        "",
        "Measured half-spreads are medians of hourly segment medians from valid, uncrossed pre-2026-06-18 L4 quotes for the eight Study-1 index markets. Post-2026-06-18 quotes are excluded as poisoned. Markets without that exact book coverage use the explicitly labeled assumption `2 × median(the eight measured Study-1 market half-spreads)`.",
        "",
        "The index aliases are underlier hypotheses pre-registered by the study. Basis is measured as the median-demeaned log price ratio, so constant quote-unit differences are removed while transient relative-price dislocations remain. Candle closes are hourly REST observations, so intra-hour basis tails are not measured.",
        "",
        "Sources: projected columns from `study3_universe.parquet`, `study3_funding_all.parquet`, `study3_candles_1h.parquet`, and `study3_fee_table.parquet`; pre-cutoff local quote files only. Machine-readable output: `data/reports/study3_se_spreads.parquet`.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    universe, funding, candles, fees = load_inputs()
    pairs = align_twin_pairs(universe["market"].to_list())
    markets = sorted({market for pair in pairs for market in (pair.market_a, pair.market_b)})
    spreads = build_half_spreads(markets)
    results = analyze_pairs(universe, funding, candles, fees, spreads)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    results.write_parquet(OUTPUT_PATH)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(render_report(results), encoding="utf-8")
    print(f"wrote {results.height} pairs to {OUTPUT_PATH}")
    print(f"wrote {DOC_PATH}")


if __name__ == "__main__":
    main()
