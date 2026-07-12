"""S-C-bis: long side of the Study-3 funding sort, with a beta benchmark.

Reuses the S-C harness (`charybdis.run_study3_carry._run_targets`) unchanged so
costs, turnover accounting, coverage handling, and 6h block clustering match the
original backtest exactly. Adds:
  - long-top-daily / long-top-8h : +1 gross long of the top funding decile
  - long-universe-daily          : equal-weight long of every eligible market
                                   (the beta benchmark)
Diagnostics: selection alpha (long-top minus long-universe, paired by period,
bootstrap CI), monthly PnL, up/down trailing-tape conditioning, and the mirror
of the reverse-causation split (where the long gains came from).
"""

from __future__ import annotations

import math
from datetime import timedelta
from pathlib import Path

import polars as pl

from charybdis import run_study3_carry as sc
from charybdis.markout import cluster_bootstrap_panel_statistic
from charybdis.study3_carry import assign_deciles

ROOT = Path(sc.ROOT)
REPORTS = ROOT / "data/reports"
OUT_BACKTEST = REPORTS / "study3_scbis_backtest.parquet"
OUT_DOC = ROOT / "docs/reports/study3_carry_bis_long_2026-07-11.md"


def spread_table_from_prior(candidates: list[str]) -> pl.DataFrame:
    prior = (
        pl.read_parquet(REPORTS / "study3_sc_backtest.parquet")
        .select("market", "market_class", "half_spread_bps", "spread_source")
        .unique()
    )
    measured = {
        r["market"]: (r["half_spread_bps"], r["spread_source"], r["market_class"])
        for r in prior.filter(pl.col("spread_source").str.starts_with("measured")).iter_rows(named=True)
    }
    assumed_vals = prior.filter(pl.col("spread_source").str.starts_with("assumed"))["half_spread_bps"].unique()
    assert assumed_vals.len() == 1, f"expected one assumed spread value, got {assumed_vals.to_list()}"
    assumed = float(assumed_vals[0])
    rows = []
    for market in sorted(set(candidates) | {"xyz:SKHX", *sc.HEDGE_MARKETS}):
        if market in measured:
            hs, src, cls = measured[market]
        else:
            hs, src, cls = assumed, "assumed_2x_study1_class_median", sc._market_class(market)
        rows.append({"market": market, "market_class": cls, "half_spread_bps": float(hs), "spread_source": src})
    return pl.DataFrame(rows)


def long_top_targets(signals: pl.DataFrame, *, long_short: bool) -> dict[str, float]:
    labels = assign_deciles(signals)
    top = labels.filter(pl.col("decile") == "top")["market"].to_list()
    return {market: 1.0 / len(top) for market in top}


def long_universe_targets(signals: pl.DataFrame, *, long_short: bool) -> dict[str, float]:
    markets = signals["market"].to_list()
    return {market: 1.0 / len(markets) for market in markets}


def period_frame(group: pl.DataFrame) -> pl.DataFrame:
    return (
        group.group_by("rebalance_time")
        .agg(
            pl.col("hold_end_time").first(),
            pl.col("funding_pnl").sum(),
            pl.col("price_pnl").sum(),
            pl.col("cost_pnl").sum(),
            pl.col("net_pnl").sum(),
        )
        .sort("rebalance_time")
        .with_columns(
            pl.col("rebalance_time").cast(pl.String).alias("cluster_key"),
            pl.col("rebalance_time").dt.hour().alias("rebalance_hour_utc"),
            ((pl.col("hold_end_time") - pl.col("rebalance_time")).dt.total_seconds() / 3600).alias("hold_hours"),
        )
    )


BOOT = {
    "strata_cols": ["rebalance_hour_utc", "hold_hours"],
    "destination_cols": ["rebalance_time", "hold_end_time"],
}


def summarize_strategy(group: pl.DataFrame, annualization: float) -> dict:
    periods = period_frame(group)
    ret_ci = cluster_bootstrap_panel_statistic(periods, statistic=lambda d: float(d["net_pnl"].sum()), **BOOT)
    sharpe_ci = cluster_bootstrap_panel_statistic(
        periods, statistic=lambda d, a=annualization: sc._sharpe(d, a), **BOOT
    )
    cumulative = periods["net_pnl"].cum_sum().to_list()
    peak = dd = 0.0
    for v in cumulative:
        peak = max(peak, float(v))
        dd = min(dd, float(v) - peak)
    return {
        "net": float(group["net_pnl"].sum()),
        "ci": (ret_ci.ci_low, ret_ci.ci_high),
        "sharpe": sharpe_ci.point_estimate,
        "sharpe_ci": (sharpe_ci.ci_low, sharpe_ci.ci_high),
        "funding": float(group["funding_pnl"].sum()),
        "price": float(group["price_pnl"].sum()),
        "cost": float(group["cost_pnl"].sum()),
        "max_dd": dd,
        "rebalances": periods.height,
        "markets": group.filter(pl.col("position") != 0)["market"].n_unique(),
        "periods": periods,
    }


def main() -> None:
    universe, funding, candles, fees, anatomy = sc.load_inputs()
    candidates = universe.filter(
        pl.col("passes_liquidity_floor") & pl.col("coverage_status").is_in(sorted(sc.ALLOWED_COVERAGE))
    )["market"].to_list()
    spreads = spread_table_from_prior(candidates)
    funding_map, candle_map = sc._maps(funding, candles)
    start = min(min(rows)[0] for market, rows in funding_map.items() if market in candidates) + timedelta(days=7)
    stop = max(row[1] for rows in candle_map.values() for row in rows)
    daily = sc._schedule(start, stop, 24)
    eight = sc._schedule(start, stop, 8)

    original_targets = sc.position_targets
    frames = []
    for name, fn, periods in [
        ("long-top-daily", long_top_targets, daily),
        ("long-top-8h", long_top_targets, eight),
        ("long-universe-daily", long_universe_targets, daily),
    ]:
        sc.position_targets = fn
        frames.append(
            sc._run_targets(
                strategy=name, periods=periods, candidates=candidates,
                funding_map=funding_map, candle_map=candle_map,
                fees=fees, spreads=spreads, long_short=False,
            )
        )
        print(f"ran {name}: {frames[-1].height} rows")
    sc.position_targets = original_targets
    backtest = pl.concat(frames, how="diagonal_relaxed")
    backtest.write_parquet(OUT_BACKTEST)

    summaries = {}
    for (name,), group in backtest.partition_by("strategy", as_dict=True).items():
        ann = 1095.0 if name.endswith("8h") else 365.0
        summaries[name] = summarize_strategy(group, ann)

    # --- selection alpha: long-top-daily minus long-universe-daily, paired ---
    top_p = summaries["long-top-daily"]["periods"].select(
        "rebalance_time", "hold_end_time", "rebalance_hour_utc", "hold_hours", "cluster_key",
        pl.col("net_pnl").alias("net_top"), pl.col("funding_pnl").alias("fund_top"),
        pl.col("price_pnl").alias("price_top"), pl.col("cost_pnl").alias("cost_top"),
    )
    uni_p = summaries["long-universe-daily"]["periods"].select(
        "rebalance_time",
        pl.col("net_pnl").alias("net_uni"), pl.col("funding_pnl").alias("fund_uni"),
        pl.col("price_pnl").alias("price_uni"), pl.col("cost_pnl").alias("cost_uni"),
    )
    paired = top_p.join(uni_p, on="rebalance_time", how="inner").with_columns(
        (pl.col("net_top") - pl.col("net_uni")).alias("net_pnl")
    )
    alpha_ci = cluster_bootstrap_panel_statistic(paired, statistic=lambda d: float(d["net_pnl"].sum()), **BOOT)
    alpha_decomp = {
        "net": float(paired["net_pnl"].sum()),
        "funding": float((paired["fund_top"] - paired["fund_uni"]).sum()),
        "price": float((paired["price_top"] - paired["price_uni"]).sum()),
        "cost": float((paired["cost_top"] - paired["cost_uni"]).sum()),
    }
    corr = float(paired.select(pl.corr("net_top", "net_uni"))[0, 0])

    # --- monthly PnL ---
    monthly = (
        pl.concat([
            summaries[s]["periods"].with_columns(pl.lit(s).alias("strategy"))
            for s in ("long-top-daily", "long-universe-daily")
        ])
        .with_columns(pl.col("rebalance_time").dt.strftime("%Y-%m").alias("month"))
        .group_by("strategy", "month")
        .agg(pl.col("net_pnl").sum(), pl.col("funding_pnl").sum(), pl.col("price_pnl").sum())
        .sort("month", "strategy")
    )

    # --- regime conditioning: trailing 7d equal-weight universe return known at rebalance ---
    tape = []
    for rebalance, _end in daily:
        rets = [
            r for m in candidates
            if (r := sc._pre_rebalance_return(candle_map.get(m, []), rebalance)) is not None
        ]
        tape.append({"rebalance_time": rebalance, "trailing_tape": sum(rets) / len(rets) if rets else None})
    tape_df = pl.DataFrame(tape)
    regime = (
        summaries["long-top-daily"]["periods"]
        .join(tape_df, on="rebalance_time", how="left")
        .join(uni_p.select("rebalance_time", "net_uni", "price_uni"), on="rebalance_time", how="left")
        .with_columns(
            pl.when(pl.col("trailing_tape") >= 0).then(pl.lit("up_tape")).otherwise(pl.lit("down_tape")).alias("trailing_regime"),
            pl.when(pl.col("price_uni") >= 0).then(pl.lit("up_period")).otherwise(pl.lit("down_period")).alias("concurrent_regime"),
        )
    )
    trailing_split = regime.group_by("trailing_regime").agg(
        pl.len().alias("periods"), pl.col("net_pnl").sum(), (pl.col("net_pnl") - pl.col("net_uni")).sum().alias("alpha")
    ).sort("trailing_regime")
    concurrent_split = regime.group_by("concurrent_regime").agg(
        pl.len().alias("periods"), pl.col("net_pnl").sum(), (pl.col("net_pnl") - pl.col("net_uni")).sum().alias("alpha")
    ).sort("concurrent_regime")

    # --- calendar halves ---
    mid = daily[len(daily) // 2][0]
    halves = (
        regime.with_columns(
            pl.when(pl.col("rebalance_time") < mid).then(pl.lit("H1")).otherwise(pl.lit("H2")).alias("half")
        )
        .group_by("half")
        .agg(pl.len().alias("periods"), pl.col("net_pnl").sum(), (pl.col("net_pnl") - pl.col("net_uni")).sum().alias("alpha"))
        .sort("half")
    )

    # --- where did the long gains come from (mirror of reverse-causation split) ---
    top_rows = backtest.filter((pl.col("strategy") == "long-top-daily") & (pl.col("position") > 0))
    pre = []
    for r in top_rows.select("market", "rebalance_time").unique().iter_rows(named=True):
        pre.append({
            "market": r["market"], "rebalance_time": r["rebalance_time"],
            "pre_ret": sc._pre_rebalance_return(candle_map.get(r["market"], []), r["rebalance_time"]),
        })
    gains = (
        top_rows.join(pl.DataFrame(pre), on=["market", "rebalance_time"], how="left")
        .filter(pl.col("price_pnl") > 0)
        .with_columns(
            pl.when(pl.col("pre_ret").is_null()).then(pl.lit("unknown"))
            .when(pl.col("pre_ret") < 0).then(pl.lit("bounce_after_drop"))
            .otherwise(pl.lit("continued_squeeze")).alias("gain_path")
        )
        .group_by("gain_path").agg(pl.col("price_pnl").sum()).sort("gain_path")
    )

    # --- print + report ---
    def pct(x):
        return "NA" if x is None else f"{100 * x:.3f}%"

    lines = [
        "# Study 3 S-C-bis: long side of the funding sort",
        "",
        "Research-only measurement from on-disk T1/T2 inputs; harness, costs, universe, schedule, and bootstrap identical to S-C (`run_study3_carry`). Long strategies pay funding and full entry/turnover costs. No out-of-sample window exists: the on-disk history (2026-01-01 to 2026-07-10) is the full S-C window, so all splits below are in-sample partitions.",
        "",
        "| Strategy | Net total return (95% CI) | Sharpe (95% CI) | Funding | Price | Cost | Max drawdown |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("long-top-daily", "long-top-8h", "long-universe-daily"):
        s = summaries[name]
        lines.append(
            f"| {name} | {pct(s['net'])} [{pct(s['ci'][0])}, {pct(s['ci'][1])}] | "
            f"{s['sharpe']:.3f} [{s['sharpe_ci'][0]:.3f}, {s['sharpe_ci'][1]:.3f}] | "
            f"{pct(s['funding'])} | {pct(s['price'])} | {pct(s['cost'])} | {pct(s['max_dd'])} |"
        )
        print(lines[-1])
    lines += [
        "",
        "## Selection alpha (long-top-daily minus long-universe-daily, paired by rebalance)",
        "",
        f"Net alpha {pct(alpha_decomp['net'])} (95% CI [{pct(alpha_ci.ci_low)}, {pct(alpha_ci.ci_high)}]); decomposition: funding {pct(alpha_decomp['funding'])}, price {pct(alpha_decomp['price'])}, cost {pct(alpha_decomp['cost'])}. Period-net correlation between the two strategies: {corr:.3f}.",
        "",
        "## Monthly net PnL",
        "",
        "| Month | long-top-daily | long-universe-daily |",
        "|---|---:|---:|",
    ]
    print(f"\nselection alpha: {pct(alpha_decomp['net'])} CI [{pct(alpha_ci.ci_low)}, {pct(alpha_ci.ci_high)}] corr {corr:.3f}")
    months = sorted(set(monthly["month"].to_list()))
    for month in months:
        row = {r["strategy"]: r["net_pnl"] for r in monthly.filter(pl.col("month") == month).iter_rows(named=True)}
        lines.append(f"| {month} | {pct(row.get('long-top-daily'))} | {pct(row.get('long-universe-daily'))} |")
        print(lines[-1])
    lines += ["", "## Regime conditioning (long-top-daily)", ""]
    lines += ["| Split | Periods | Net PnL | Alpha vs universe |", "|---|---:|---:|---:|"]
    for frame, label in ((trailing_split, "trailing_regime"), (concurrent_split, "concurrent_regime"), (halves, "half")):
        for r in frame.iter_rows(named=True):
            lines.append(f"| {r[label]} | {r['periods']} | {pct(r['net_pnl'])} | {pct(r['alpha'])} |")
            print(lines[-1])
    lines += [
        "",
        "Trailing regime uses the equal-weight universe close-to-close return over the seven days known at rebalance (sign split). Concurrent regime uses the same-period long-universe price PnL sign and is descriptive only (not tradeable).",
        "",
        "## Where the long gains came from (mirror of the S-C reverse-causation split)",
        "",
        "| Gain path | Long price gains |",
        "|---|---:|",
    ]
    for r in gains.iter_rows(named=True):
        lines.append(f"| {r['gain_path']} | {pct(r['price_pnl'])} |")
        print(lines[-1])
    lines += [
        "",
        "`bounce_after_drop` gains come from names whose trailing seven-day return was negative at entry (S-C interpretation B, reverse causation); `continued_squeeze` gains come from names still rising at entry (interpretation A, funding as squeeze compensation).",
        "",
        "## Provenance",
        "",
        "Inputs: `study3_universe.parquet`, `study3_funding_all.parquet`, `study3_candles_1h.parquet`, `study3_fee_table.parquet`, spread table reconstructed from `study3_sc_backtest.parquet` (7 measured markets, uniform assumed value elsewhere). Output: `study3_scbis_backtest.parquet`. No network calls or paid data; terminal open positions incur no liquidation cost (same convention as S-C).",
    ]
    OUT_DOC.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {OUT_DOC}")


if __name__ == "__main__":
    main()
